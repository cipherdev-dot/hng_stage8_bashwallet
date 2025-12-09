

import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings model.

    All configuration variables are loaded from environment variables
    with fallback defaults for development.
    """

    # Database
    database_url: str = os.getenv("DATABASE_URL", "YOUR_DEFAULT_DATABASE_URL")

    # JWT settings
    secret_key: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # API Key settings
    api_key_salt: str = os.getenv("API_KEY_SALT", "your-api-key-salt-change-in-production")

    # Google OAuth settings
    google_client_id: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "your-redirect-uri")

    # Paystack settings
    paystack_secret_key: str = os.getenv("PAYSTACK_SECRET_KEY", "sk_test_your-secret-key")
    paystack_public_key: str = os.getenv("PAYSTACK_PUBLIC_KEY", "pk_test_your-public-key")
    paystack_base_url: str = os.getenv("PAYSTACK_BASE_URL", "your-paystack-base-url")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
settings = Settings()
