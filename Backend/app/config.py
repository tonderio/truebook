from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str = "supersecretkey_afinops_tonder_2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    MONGO_URI: str
    MONGO_DATABASE: str = "pdn"
    MONGO_COLLECTION: str = "mv_payment_transactions"
    MONGO_CONNECT_TIMEOUT_MS: int = 60000
    MONGO_SOCKET_TIMEOUT_MS: int = 60000

    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    AWS_SETTLEMENTS_TABLE: Optional[str] = None
    AWS_SETTLEMENTS_DATE_FIELD: Optional[str] = None
    AWS_SETTLEMENTS_AMOUNT_FIELD: Optional[str] = None
    AWS_SETTLEMENTS_MERCHANT_FIELD: Optional[str] = None

    UPLOAD_DIR: str = "uploads"

    # Kushki SFTP ingestion
    KUSHKI_SFTP_ENABLED: bool = False
    KUSHKI_SFTP_HOST: Optional[str] = None
    KUSHKI_SFTP_PORT: int = 22
    KUSHKI_SFTP_USERNAME: Optional[str] = None
    KUSHKI_SFTP_PRIVATE_KEY_PATH: Optional[str] = None
    KUSHKI_SFTP_PRIVATE_KEY: Optional[str] = None  # key content as env var (overrides PATH)
    KUSHKI_SFTP_PRIVATE_KEY_PASSPHRASE: Optional[str] = None
    KUSHKI_SFTP_REMOTE_DIR: str = "/Mensual"
    KUSHKI_SFTP_TIMEOUT_SECONDS: int = 30
    KUSHKI_SFTP_STRICT_HOST_KEY: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
