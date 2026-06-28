import phonenumbers
from twilio.rest import Client

from .config import settings

_client = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def normalize_phone(raw: str) -> str:
    """Parse a possibly-local number into E.164 (e.g. '054-123-4567' -> '+972541234567')."""
    try:
        parsed = phonenumbers.parse(raw, settings.default_region)
    except phonenumbers.NumberParseException:
        raise ValueError(f"Invalid phone number: {raw!r}")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Invalid phone number: {raw!r}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def send_sms(to: str, body: str):
    return client().messages.create(
        to=to,
        from_=settings.twilio_from_number,
        body=body,
    )


def place_call(to: str):
    """Start an outbound call; Twilio fetches TwiML from our /webhooks/voice."""
    base = settings.public_base_url.rstrip("/")
    return client().calls.create(
        to=to,
        from_=settings.twilio_from_number,
        url=f"{base}/webhooks/voice",
        status_callback=f"{base}/webhooks/call-status",
        status_callback_event=["completed", "no-answer", "failed", "busy"],
    )
