from pathlib import Path
import ipaddress

from pydantic import SecretStr, field_validator
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
    pte_lan_mode: bool = False
    pte_lan_bind_ip: str = "127.0.0.1"
    pte_lan_port: int = 8765
    pte_lan_username: str = "pte"
    pte_lan_password: SecretStr = SecretStr("")

    @field_validator("pte_lan_bind_ip")
    @classmethod
    def private_bind_address(cls, value: str) -> str:
        address = ipaddress.ip_address(value)
        allowed = [ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")]
        if address.version != 4 or not any(address in network for network in allowed):
            raise ValueError("LAN bind IP must be a private IPv4 address")
        return value

    @property
    def data_dir(self) -> Path:
        return (PROJECT_ROOT / self.pte_data_dir).resolve()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "db" / "pte.sqlite3"
