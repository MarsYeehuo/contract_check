from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

for _candidate in (PROJECT_DIR / ".env", BACKEND_DIR / ".env"):
    if _candidate.is_file():
        load_dotenv(_candidate, override=False)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path
    return default.resolve()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    rules_path: Path
    samples_dir: Path
    max_text_chars: int
    llm_enabled: bool
    anthropic_api_key: str | None
    anthropic_model: str
    llm_timeout_seconds: float
    llm_max_contract_chars: int
    cors_origins: tuple[str, ...]
    anthropic_base_url: str | None = None
    anthropic_auth_token: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
        origins = tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        )
        return cls(
            data_dir=_env_path("DATA_DIR", BACKEND_DIR.parent / "data"),
            rules_path=_env_path(
                "RULES_PATH", BACKEND_DIR / "rules" / "review_rules.yaml"
            ),
            samples_dir=_env_path("SAMPLES_DIR", BACKEND_DIR / "samples"),
            max_text_chars=_env_int("MAX_TEXT_CHARS", 200_000),
            llm_enabled=_env_bool("LLM_ENABLED", True),
            anthropic_api_key=api_key,
            anthropic_model=os.getenv(
                "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
            ).strip(),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
            llm_max_contract_chars=_env_int("LLM_MAX_CONTRACT_CHARS", 50_000),
            cors_origins=origins,
            anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", "").strip()
            or None,
            anthropic_auth_token=os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip()
            or None,
        )
