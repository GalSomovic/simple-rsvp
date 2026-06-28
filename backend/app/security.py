from fastapi import Header, HTTPException, Request, status
from twilio.request_validator import RequestValidator

from .config import settings


def require_access_code(x_access_code: str = Header(default="")):
    """Gate organiser endpoints behind the shared code typed into the frontend."""
    if x_access_code != settings.access_code:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad access code")


async def verify_twilio_signature(request: Request):
    """Validate that an inbound webhook genuinely came from Twilio."""
    if not settings.validate_twilio_signature:
        return
    validator = RequestValidator(settings.twilio_auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    # Twilio signs the full public URL it called, plus the POSTed form params.
    url = settings.public_base_url.rstrip("/") + request.url.path
    form = await request.form()
    params = {k: v for k, v in form.items()}
    if not validator.validate(url, params, signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")
