from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres
    database_url: str = "postgresql+psycopg2://rsvp:rsvp@localhost:5432/rsvp"

    # Organiser auth (shared code typed into the frontend)
    access_code: str = "change-me"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""  # E.164, e.g. +12025550123

    # Public base URL of THIS backend, reachable by Twilio via the Cloudflare tunnel.
    # Used to build webhook + media (<Play>) URLs. e.g. https://rsvp-api.example.com
    public_base_url: str = "http://localhost:8000"

    # Default region for parsing local phone numbers into E.164 (Israel).
    default_region: str = "IL"

    # Message sent over SMS. {name} is substituted per guest.
    sms_template: str = (
        "Hi {name}! You're invited to our wedding. "
        "Reply 1 if you're coming, or 2 if you can't make it."
    )

    # Validate inbound Twilio webhook signatures. Disable only for local testing.
    validate_twilio_signature: bool = True


settings = Settings()
