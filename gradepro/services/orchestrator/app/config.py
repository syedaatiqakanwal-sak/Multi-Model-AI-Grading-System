import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://app_rw:gradepro_dev_password@pgbouncer:5432/gradepro"
    REDIS_URL: str = "redis://redis:6379/0"

    ML_INFERENCE_URL: str = "http://ml_inference:8002"
    PDF_SERVICE_URL: str = "http://pdf_service:8003"
    GOTENBERG_URL: str = "http://gotenberg:3000"
    CLAMAV_SOCKET: str = "/var/run/clamav/clamd.ctl"

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY: str = ""
    R2_SECRET_KEY: str = ""
    R2_BUCKET_ASSIGNMENTS: str = "gradepro-assignments"
    R2_BUCKET_REPORTS: str = "gradepro-reports"
    R2_BUCKET_TEMPLATES: str = "gradepro-templates"

    # LLM and Timeouts
    LLM_CALL_TIMEOUT_SECONDS: int = 20

    # Local HuggingFace models (AI detector + plagiarism SBERT)
    MODELS_DIR: str = "./models"
    AI_DETECTION_REFER_THRESHOLD: float = 0.7
    PLAGIARISM_REFER_THRESHOLD: float = 20.0

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
