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

    # Internal API key for BFF proxy (TrueBook v2)
    INTERNAL_API_KEY: Optional[str] = None

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

    # STP SFTP (withdrawals — pending credentials)
    STP_SFTP_ENABLED: bool = False
    STP_SFTP_HOST: Optional[str] = None
    STP_SFTP_PORT: int = 22
    STP_SFTP_USERNAME: Optional[str] = None
    STP_SFTP_PRIVATE_KEY: Optional[str] = None
    STP_SFTP_REMOTE_DIR: str = "/"
    STP_SFTP_TIMEOUT_SECONDS: int = 30

    # Pagsmile / OXXO Pay SFTP (pending credentials)
    PAGSMILE_SFTP_ENABLED: bool = False
    PAGSMILE_SFTP_HOST: Optional[str] = None
    PAGSMILE_SFTP_PORT: int = 22
    PAGSMILE_SFTP_USERNAME: Optional[str] = None
    PAGSMILE_SFTP_PRIVATE_KEY: Optional[str] = None
    PAGSMILE_SFTP_REMOTE_DIR: str = "/"
    PAGSMILE_SFTP_TIMEOUT_SECONDS: int = 30

    # Paysafe SFTP (no transactions expected)
    PAYSAFE_SFTP_ENABLED: bool = False
    PAYSAFE_SFTP_HOST: Optional[str] = None
    PAYSAFE_SFTP_PORT: int = 22
    PAYSAFE_SFTP_USERNAME: Optional[str] = None
    PAYSAFE_SFTP_PRIVATE_KEY: Optional[str] = None
    PAYSAFE_SFTP_REMOTE_DIR: str = "/"

    # Bitso Payouts & Funding API (SPEI v2)
    BITSO_API_ENABLED: bool = False
    BITSO_API_KEY: Optional[str] = None
    BITSO_API_SECRET: Optional[str] = None
    BITSO_API_BASE_URL: str = "https://api.bitso.com"
    BITSO_API_TIMEOUT_SECONDS: int = 30

    # Warren AI Agent (Anthropic Claude)
    ANTHROPIC_API_KEY: Optional[str] = None

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
