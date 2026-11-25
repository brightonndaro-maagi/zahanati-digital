import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", 15)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", 7)))
    PASSWORD_RESET_MINUTES = int(os.environ.get("PASSWORD_RESET_MINUTES", 30))
    CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = True
    CLINIC_TIMEZONE = os.environ.get("CLINIC_TIMEZONE", "Africa/Dar_es_Salaam")
    APPOINTMENT_SLOT_MINUTES = int(os.environ.get("APPOINTMENT_SLOT_MINUTES", 30))
    APPOINTMENT_MIN_LEAD_MINUTES = int(os.environ.get("APPOINTMENT_MIN_LEAD_MINUTES", 60))
    APPOINTMENT_MAX_ADVANCE_DAYS = int(os.environ.get("APPOINTMENT_MAX_ADVANCE_DAYS", 90))
    # OTP rules (see spec 3.1)
    OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", 300))
    OTP_RESEND_SECONDS = int(os.environ.get("OTP_RESEND_SECONDS", 60))
    OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", 5))
    OTP_LOCK_SECONDS = int(os.environ.get("OTP_LOCK_SECONDS", 600))
    # SMS: console (dev only, prints the code in the server log) | beem (production) | memory (tests)
    SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "console")
    BEEM_API_KEY = os.environ.get("BEEM_API_KEY")
    BEEM_SECRET_KEY = os.environ.get("BEEM_SECRET_KEY")
    BEEM_SOURCE_ADDR = os.environ.get("BEEM_SOURCE_ADDR")
    # Orders (spec 3.3, 10): 1-20 medicines per order; unpaid orders expire after 24 h
    ORDER_EXPIRY_HOURS = int(os.environ.get("ORDER_EXPIRY_HOURS", 24))
    ORDER_MAX_ITEMS = int(os.environ.get("ORDER_MAX_ITEMS", 20))
    ORDER_MAX_ITEM_QUANTITY = int(os.environ.get("ORDER_MAX_ITEM_QUANTITY", 20))
    # Prescription files (spec 3.4): PDF/JPG/PNG up to 5 MB, encrypted, deleted after 2 years
    PRESCRIPTION_MAX_BYTES = int(os.environ.get("PRESCRIPTION_MAX_BYTES", 5 * 1024 * 1024))
    PRESCRIPTION_RETENTION_DAYS = int(os.environ.get("PRESCRIPTION_RETENTION_DAYS", 730))
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "instance/prescriptions")
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024  # request size cap (file limit itself is PRESCRIPTION_MAX_BYTES)
    # Comma-separated Fernet keys: the first encrypts, all of them decrypt (key rotation). `flask generate-fernet-key`
    FILE_ENCRYPTION_KEYS = [k.strip() for k in os.environ.get("FILE_ENCRYPTION_KEYS", "").split(",") if k.strip()]
    # Payments: provider adapter + callback protection (HMAC-SHA256 of the raw body in header X-Signature)
    PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "simulator")
    ALLOW_PAYMENT_SIMULATOR = os.environ.get("ALLOW_PAYMENT_SIMULATOR", "false").lower() == "true"
    PAYMENT_CALLBACK_SECRET = os.environ.get("PAYMENT_CALLBACK_SECRET")
    PAYMENT_NETWORKS = [n.strip() for n in os.environ.get("PAYMENT_NETWORKS", "mpesa,tigopesa").split(",") if n.strip()]
    PAYMENT_TIMEOUT_MINUTES = int(os.environ.get("PAYMENT_TIMEOUT_MINUTES", 30))
    # Chat / prescriptions
    CHAT_REPLY_TARGET_HOURS = int(os.environ.get("CHAT_REPLY_TARGET_HOURS", 24))
    CHAT_MAX_MESSAGE_CHARS = int(os.environ.get("CHAT_MAX_MESSAGE_CHARS", 2000))
    PRESCRIPTION_VALID_DAYS = int(os.environ.get("PRESCRIPTION_VALID_DAYS", 90))
    HEDHI_INACTIVITY_DAYS = int(os.environ.get("HEDHI_INACTIVITY_DAYS", 730))
    HEDHI_MAX_ENTRIES = int(os.environ.get("HEDHI_MAX_ENTRIES", 120))
    PROXY_HOPS = int(os.environ.get("PROXY_HOPS", 0))  # number of trusted reverse proxies in front of the app (nginx/caddy = 1)
    DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "en")  # language of API messages when the client sends none
    SWAGGER_ENABLED = os.environ.get("SWAGGER_ENABLED", "true").lower() == "true"
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True
    # Doctor appointments exist in the first spec but are outside the MVP of the second: switch them off with FEATURE_APPOINTMENTS=false
    FEATURE_APPOINTMENTS = os.environ.get("FEATURE_APPOINTMENTS", "true").lower() == "true"
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    pass


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret-key-with-32-chars!!"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    RATELIMIT_ENABLED = False
    SMS_PROVIDER = "memory"
    PAYMENT_CALLBACK_SECRET = "test-callback-secret"
    FILE_ENCRYPTION_KEYS = ["sjQrgjA9mxPvGkpeyJuRGCA0R86no4QEjudRQUhs3Ks="]  # test-only key


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
