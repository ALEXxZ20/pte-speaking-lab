from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    pte_data_dir: Path = Path("data")
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    max_audio_mb: int = 100
    max_audio_seconds: int = 120
    pause_min_ms: int = 250
    long_pause_ms: int = 500
    very_long_pause_ms: int = 1000
    cross_dimension_window_ms: int = 750
    llm_provider: str = "openai"
    alignment_provider: str = "none"
    pronunciation_provider: str = "none"
    asr_provider: str = "none"
    openai_api_key: SecretStr = SecretStr("")
    openai_analysis_model: str = ""

    @property
    def data_dir(self) -> Path:
        return (PROJECT_ROOT / self.pte_data_dir).resolve()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "db" / "pte.sqlite3"
