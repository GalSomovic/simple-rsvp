# 💍 Wedding RSVP

Text your guest list, collect 1 = coming / 2 = not coming, and auto-call anyone
who doesn't reply to play a voice recording and capture their keypress.

- **Channel:** Twilio SMS (+ outbound voice calls for non-responders)
- **Backend:** FastAPI + Postgres
- **Frontend:** React (single dashboard), gated by a shared access code
- **Deploy:** Kubernetes (on-prem), exposed via your Cloudflare Tunnel

## How it works

```
1. Organiser pastes guests, sets SMS text, uploads a voice recording
2. "Send SMS"            -> texts every pending guest: reply 1=coming / 2=not coming
3. Guest replies 1/2     -> /webhooks/sms updates their RSVP
4. "Call non-responders" -> calls everyone still pending
5. Call answered         -> <Play> recording, <Gather> one keypress -> RSVP updated
```

Guest state: `rsvp_status` (pending/going/not_going), `sms_status`, `call_status`.

## Prerequisites

- A **Twilio account** with:
  - An SMS-capable phone number (also voice-capable for the call step).
  - Account SID + Auth Token (Console home page).
- A public image registry (e.g. **Docker Hub**) to push the two images to — the
  Talos node has no in-cluster registry or pull secrets, so it pulls from a registry.
- Your **Cloudflare Tunnel** with a hostname (e.g. `rsvp.example.com`) free to use.

> **Target cluster (`gals-cluster`):** single-node Talos (`talos-aq5-onz`). The
> manifests are already adapted to it — pods tolerate the control-plane taint,
> Postgres persists via a `hostPath` under `/var` (no dynamic storage on this node),
> and ingress is the existing token-based Cloudflare Tunnel in the `default` namespace.

> ⚠️ **Note on Twilio trial accounts:** a trial can only message *verified* numbers
> and prepends a trial banner. Upgrade before the real send.

## Twilio configuration

You do **not** need to set webhook URLs in the Twilio console for this app:
- SMS replies: set the **"A message comes in"** webhook on your number to
  `https://rsvp.example.com/webhooks/sms` (HTTP POST).
- Voice: the call step passes its TwiML URL programmatically, so no console setup
  is needed for outbound calls.

Signature validation is on by default (`VALIDATE_TWILIO_SIGNATURE=true`); it uses
your Auth Token, so keep `PUBLIC_BASE_URL` exactly equal to the public hostname
Twilio calls.

## Local development

```bash
# 1. Postgres
docker run --rm -e POSTGRES_USER=rsvp -e POSTGRES_PASSWORD=rsvp -e POSTGRES_DB=rsvp \
  -p 5432:5432 postgres:16-alpine

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in Twilio creds; set VALIDATE_TWILIO_SIGNATURE=false for local
uvicorn app.main:app --reload

# 3. Frontend (proxies /api to localhost:8000)
cd frontend
npm install
npm run dev
```

To test webhooks locally, point a tunnel (cloudflared / ngrok) at `localhost:8000`
and set `PUBLIC_BASE_URL` to that URL.

## Deploy to Kubernetes

All commands use the cluster context `admin@gals-cluster`.

```bash
# 1. Images are built & pushed to GHCR automatically by GitHub Actions
#    (.github/workflows/build.yml) on every push to main:
#      ghcr.io/galsomovic/simple-rsvp-backend:latest
#      ghcr.io/galsomovic/simple-rsvp-frontend:latest
#    Both packages are public, so the Talos node pulls them with no pull secret.

# 2. Namespace
kubectl --context admin@gals-cluster apply -f k8s/namespace.yaml

# 3. Secrets — copy the example, fill real values, DO NOT commit the filled file
cp k8s/secrets.example.yaml k8s/secrets.yaml   # edit, then:
kubectl --context admin@gals-cluster apply -f k8s/secrets.yaml

# 4. Set PUBLIC_BASE_URL in k8s/backend.yaml to your real https://rsvp.<domain>, then:
kubectl --context admin@gals-cluster apply -f k8s/postgres.yaml
kubectl --context admin@gals-cluster apply -f k8s/backend.yaml
kubectl --context admin@gals-cluster apply -f k8s/frontend.yaml

kubectl --context admin@gals-cluster -n wedding-rsvp get pods -w
```

Finally, add a **Public Hostname** to your Cloudflare Tunnel in the Zero Trust
dashboard pointing `rsvp.<domain>` → `rsvp-frontend.wedding-rsvp.svc.cluster.local:80`.
Full details (and why there's no Ingress manifest) are in `k8s/ingress.yaml`.

## Day-of checklist

1. Open `https://rsvp.example.com`, enter the access code.
2. Paste the guest list (`Name, phone` per line), confirm phone numbers parsed.
3. Set the SMS message and upload the voice recording.
4. Click **Send SMS to pending**. Watch statuses flip as replies arrive.
5. After a while, click **Call non-responders** to ring everyone still pending.
6. Use the per-row dropdown to manually fix any RSVP you hear about in person.

## Things to keep in mind

- **Costs:** each SMS and each call-minute costs money; international rates vary.
- **Quiet hours:** don't trigger the call step in the middle of the night.
- **Opt-out:** Twilio auto-handles STOP for SMS compliance.
- **Idempotency:** re-clicking "Send SMS" only targets guests not already sent.
