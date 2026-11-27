from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VideoMind AI"
    environment: str = "development"
    secret_key: str = "change-this-development-secret-before-deployment"
    access_token_expire_minutes: int = 1440
    database_url: str = "sqlite:///./videomind.db"
    uploads_dir: str = "../storage/uploads"
    max_upload_mb: int = 500
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimensions: int = 384
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o-mini"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Slide Extraction Settings
    slides_enabled: bool = True
    slides_dir: str = "../storage/slides"
    temp_dir: str = "../storage/temp"
    slide_sample_fps: float = 1.0
    slide_output_width: int = 1280
    slide_max_concurrent_jobs: int = 2
    slide_min_interval_seconds: float = 1.5
    slide_detection_threshold: float = 0.02
    slide_max_video_size_mb: int = 500
    slide_max_duration_minutes: int = 240
    slide_similarity_threshold: float = 0.88
    slide_max_extracted: int = 200

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
