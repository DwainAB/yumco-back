from pydantic import field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int
    MAIL_SERVER: str
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-5.4-mini"
    OPENAI_WEB_SEARCH_MODEL: str = "gpt-4.1-mini"
    APP_BASE_URL: str | None = None
    FRONTEND_BASE_URL: str | None = None
    CORS_ALLOWED_ORIGINS: list[str] = [
        "https://dashboard.yumco.fr",
        "https://platform.yumco.fr",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_STARTER_MONTHLY: str | None = None
    STRIPE_PRICE_STARTER_YEARLY: str | None = None
    STRIPE_PRICE_PRO_AI_MONTHLY: str | None = None
    STRIPE_PRICE_PRO_AI_YEARLY: str | None = None
    STRIPE_PRICE_BUSINESS_AI_MONTHLY: str | None = None
    STRIPE_PRICE_BUSINESS_AI_YEARLY: str | None = None
    STRIPE_PRICE_TABLET_RENTAL_MONTHLY: str | None = None
    STRIPE_PRICE_TABLET_RENTAL_YEARLY: str | None = None
    STRIPE_PRICE_PRINTER_RENTAL_MONTHLY: str | None = None
    STRIPE_PRICE_PRINTER_RENTAL_YEARLY: str | None = None
    BREVO_API_KEY: str | None = None
    HUBRISE_CLIENT_ID: str | None = None
    HUBRISE_CLIENT_SECRET: str | None = None
    HUBRISE_REDIRECT_URI: str | None = "http://192.168.1.45:8000/integrations/hubrise/callback"
    HUBRISE_RESULT_REDIRECT_URI: str | None = None
    HUBRISE_WEBHOOK_URL: str | None = None

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    class Config: 
        env_file = ".env"

settings = Settings()
