"""Portable settings for any OpenAI-compatible chat completions endpoint."""
from dataclasses import dataclass
import math
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_url: str = "http://127.0.0.1:8000/v1"
    api_key: str = "local"
    model: str = "local-model"
    database_path: Path = Path("data/notebook.sqlite3")
    timeout_seconds: float = 90
    max_tokens: int = 512

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("OPENAI_BASE_URL must not be empty")
        if not self.api_key.strip():
            raise ValueError("OPENAI_API_KEY must not be empty")
        if not self.model.strip():
            raise ValueError("OPENAI_MODEL must not be empty")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS must be finite and positive")
        if not isinstance(self.max_tokens, int) or not 1 <= self.max_tokens <= 4096:
            raise ValueError("OPENAI_MAX_TOKENS must be an integer between 1 and 4096")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            base_url=os.getenv("OPENAI_BASE_URL", cls.base_url),
            api_key=os.getenv("OPENAI_API_KEY", cls.api_key),
            model=os.getenv("OPENAI_MODEL", cls.model),
            database_path=Path(os.getenv("NOTEBOOK_DB_PATH", str(cls.database_path))),
            timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", str(cls.timeout_seconds))),
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", str(cls.max_tokens))),
        )
