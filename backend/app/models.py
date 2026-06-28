from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from .db import Base


def _now():
    return datetime.now(timezone.utc)


# rsvp_status:  pending | going | not_going
# sms_status:   not_sent | sent | replied | failed
# call_status:  not_called | calling | answered | no_answer | failed
class Guest(Base):
    __tablename__ = "guests"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(32), nullable=False, unique=True, index=True)  # E.164

    rsvp_status = Column(String(16), nullable=False, default="pending")
    sms_status = Column(String(16), nullable=False, default="not_sent")
    call_status = Column(String(16), nullable=False, default="not_called")

    note = Column(Text, nullable=True)  # free text, e.g. raw reply / error
    last_contacted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "rsvp_status": self.rsvp_status,
            "sms_status": self.sms_status,
            "call_status": self.call_status,
            "note": self.note,
            "last_contacted_at": self.last_contacted_at.isoformat()
            if self.last_contacted_at
            else None,
        }


# Single-row table holding event-wide settings the organiser edits in the UI:
# the SMS text and the uploaded voice recording.
class EventConfig(Base):
    __tablename__ = "event_config"

    id = Column(Integer, primary_key=True)
    sms_template = Column(Text, nullable=True)
    recording_mime = Column(String(64), nullable=True)
    recording = Column(Text, nullable=True)  # base64-encoded audio bytes
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
