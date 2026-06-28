import base64

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import Gather, VoiceResponse

from . import twilio_service
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import EventConfig, Guest
from .security import require_access_code, verify_twilio_signature

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Wedding RSVP")


def get_config(db: Session) -> EventConfig:
    cfg = db.query(EventConfig).first()
    if cfg is None:
        cfg = EventConfig(sms_template=settings.sms_template)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# --------------------------------------------------------------------------
# Organiser API (gated by shared access code)
# --------------------------------------------------------------------------
@app.get("/api/login", dependencies=[Depends(require_access_code)])
def login():
    return {"ok": True}


@app.get("/api/guests", dependencies=[Depends(require_access_code)])
def list_guests(db: Session = Depends(get_db)):
    guests = db.query(Guest).order_by(Guest.name).all()
    return [g.to_dict() for g in guests]


@app.get("/api/stats", dependencies=[Depends(require_access_code)])
def stats(db: Session = Depends(get_db)):
    guests = db.query(Guest).all()
    out = {"total": len(guests), "going": 0, "not_going": 0, "pending": 0}
    for g in guests:
        out[g.rsvp_status] = out.get(g.rsvp_status, 0) + 1
    return out


@app.post("/api/guests/import", dependencies=[Depends(require_access_code)])
def import_guests(payload: dict, db: Session = Depends(get_db)):
    """Bulk add guests. Accepts {"guests": [{"name","phone"}, ...]}."""
    added, skipped, errors = 0, 0, []
    for row in payload.get("guests", []):
        name = (row.get("name") or "").strip()
        raw_phone = (row.get("phone") or "").strip()
        if not name or not raw_phone:
            continue
        try:
            phone = twilio_service.normalize_phone(raw_phone)
        except ValueError as e:
            errors.append(str(e))
            continue
        if db.query(Guest).filter(Guest.phone == phone).first():
            skipped += 1
            continue
        db.add(Guest(name=name, phone=phone))
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped, "errors": errors}


@app.delete("/api/guests/{guest_id}", dependencies=[Depends(require_access_code)])
def delete_guest(guest_id: int, db: Session = Depends(get_db)):
    g = db.get(Guest, guest_id)
    if not g:
        raise HTTPException(404, "Not found")
    db.delete(g)
    db.commit()
    return {"ok": True}


@app.post("/api/guests/{guest_id}/status", dependencies=[Depends(require_access_code)])
def set_status(guest_id: int, payload: dict, db: Session = Depends(get_db)):
    """Manual override, e.g. organiser knows someone's answer."""
    g = db.get(Guest, guest_id)
    if not g:
        raise HTTPException(404, "Not found")
    status = payload.get("rsvp_status")
    if status not in ("pending", "going", "not_going"):
        raise HTTPException(400, "bad status")
    g.rsvp_status = status
    db.commit()
    return g.to_dict()


@app.get("/api/config", dependencies=[Depends(require_access_code)])
def read_config(db: Session = Depends(get_db)):
    cfg = get_config(db)
    return {
        "sms_template": cfg.sms_template,
        "has_recording": bool(cfg.recording),
    }


@app.put("/api/config", dependencies=[Depends(require_access_code)])
def update_config(payload: dict, db: Session = Depends(get_db)):
    cfg = get_config(db)
    if "sms_template" in payload:
        cfg.sms_template = payload["sms_template"]
    db.commit()
    return {"ok": True}


@app.post("/api/config/recording", dependencies=[Depends(require_access_code)])
async def upload_recording(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    data = await file.read()
    cfg = get_config(db)
    cfg.recording = base64.b64encode(data).decode()
    cfg.recording_mime = file.content_type or "audio/mpeg"
    db.commit()
    return {"ok": True, "bytes": len(data)}


# --------------------------------------------------------------------------
# Actions — kick off outreach in the background, statuses flip as they run
# --------------------------------------------------------------------------
@app.post("/api/actions/send-sms", dependencies=[Depends(require_access_code)])
def action_send_sms(bg: BackgroundTasks, db: Session = Depends(get_db)):
    targets = (
        db.query(Guest.id)
        .filter(Guest.rsvp_status == "pending", Guest.sms_status.in_(["not_sent", "failed"]))
        .all()
    )
    ids = [t[0] for t in targets]
    bg.add_task(_send_sms_batch, ids)
    return {"queued": len(ids)}


@app.post(
    "/api/actions/call-nonresponders", dependencies=[Depends(require_access_code)]
)
def action_call(bg: BackgroundTasks, db: Session = Depends(get_db)):
    targets = (
        db.query(Guest.id)
        .filter(Guest.rsvp_status == "pending", Guest.call_status != "calling")
        .all()
    )
    ids = [t[0] for t in targets]
    bg.add_task(_call_batch, ids)
    return {"queued": len(ids)}


def _send_sms_batch(ids):
    db = SessionLocal()
    try:
        cfg = get_config(db)
        template = cfg.sms_template or settings.sms_template
        for gid in ids:
            g = db.get(Guest, gid)
            if not g:
                continue
            try:
                twilio_service.send_sms(g.phone, template.format(name=g.name))
                g.sms_status = "sent"
            except Exception as e:  # noqa: BLE001
                g.sms_status = "failed"
                g.note = f"sms error: {e}"
            db.commit()
    finally:
        db.close()


def _call_batch(ids):
    db = SessionLocal()
    try:
        for gid in ids:
            g = db.get(Guest, gid)
            if not g:
                continue
            try:
                twilio_service.place_call(g.phone)
                g.call_status = "calling"
            except Exception as e:  # noqa: BLE001
                g.call_status = "failed"
                g.note = f"call error: {e}"
            db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Media — Twilio fetches the recording here for <Play>
# --------------------------------------------------------------------------
@app.get("/media/recording")
def media_recording(db: Session = Depends(get_db)):
    cfg = get_config(db)
    if not cfg.recording:
        raise HTTPException(404, "No recording uploaded")
    return Response(
        content=base64.b64decode(cfg.recording),
        media_type=cfg.recording_mime or "audio/mpeg",
    )


# --------------------------------------------------------------------------
# Twilio webhooks (validated by signature)
# --------------------------------------------------------------------------
def _match_guest(db: Session, phone: str):
    return db.query(Guest).filter(Guest.phone == phone).first()


def _apply_digit(g: Guest, digit: str) -> bool:
    if digit == "1":
        g.rsvp_status = "going"
    elif digit == "2":
        g.rsvp_status = "not_going"
    else:
        return False
    return True


@app.post("/webhooks/sms", dependencies=[Depends(verify_twilio_signature)])
async def webhook_sms(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    from_number = form.get("From", "")
    body = (form.get("Body", "") or "").strip()
    g = _match_guest(db, from_number)
    resp = VoiceResponse()  # MessagingResponse would also work; empty TwiML is fine
    if g and _apply_digit(g, body[:1]):
        g.sms_status = "replied"
        g.note = f"sms reply: {body}"
        db.commit()
    return Response(content=str(resp), media_type="application/xml")


@app.post("/webhooks/voice", dependencies=[Depends(verify_twilio_signature)])
async def webhook_voice():
    """TwiML: play the recording, then capture a single keypress."""
    base = settings.public_base_url.rstrip("/")
    vr = VoiceResponse()
    gather = Gather(num_digits=1, action="/webhooks/voice/gather", method="POST")
    gather.play(f"{base}/media/recording")
    vr.append(gather)
    # If no input, replay once.
    vr.redirect("/webhooks/voice")
    return Response(content=str(vr), media_type="application/xml")


@app.post("/webhooks/voice/gather", dependencies=[Depends(verify_twilio_signature)])
async def webhook_voice_gather(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    to_number = form.get("To", "")  # the guest we called
    digit = (form.get("Digits", "") or "")[:1]
    g = _match_guest(db, to_number)
    vr = VoiceResponse()
    if g and _apply_digit(g, digit):
        g.call_status = "answered"
        g.note = f"voice press: {digit}"
        db.commit()
        vr.say("Thank you! Your response has been recorded. Goodbye.")
        vr.hangup()
    else:
        vr.say("Sorry, I didn't get that.")
        vr.redirect("/webhooks/voice")
    return Response(content=str(vr), media_type="application/xml")


@app.post("/webhooks/call-status", dependencies=[Depends(verify_twilio_signature)])
async def webhook_call_status(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    to_number = form.get("To", "")
    call_status = form.get("CallStatus", "")
    g = _match_guest(db, to_number)
    if g and g.call_status == "calling":
        # Only downgrade if they never pressed a key (still pending).
        if call_status in ("no-answer", "busy", "failed", "canceled"):
            g.call_status = "no_answer"
            db.commit()
    return Response(status_code=204)


@app.get("/healthz")
def healthz():
    return {"ok": True}
