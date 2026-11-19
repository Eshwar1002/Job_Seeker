import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# httpx (used by chromadb's model download) misparses bracketed IPv6 entries
# like [::1] in NO_PROXY on Windows — strip them before any HTTP client loads.
for _var in ("NO_PROXY", "no_proxy"):
    _val = os.environ.get(_var)
    if _val and "[" in _val:
        os.environ[_var] = ",".join(p for p in _val.split(",") if "[" not in p)

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    hf_token: str = ""
    hf_model: str = "Qwen/Qwen2.5-7B-Instruct"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    default_country: str = "India"
    default_hours_old: int = 168
    default_results_per_site: int = 30

    data_dir: str = "data"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_path / 'jobpilot.db'}"

    @property
    def chroma_path(self) -> Path:
        p = self.data_path / "chroma"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()