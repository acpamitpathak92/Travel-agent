"""Environment-driven configuration. No secrets are ever hardcoded.

The .env file is loaded here (before any setting is read) so running
`uvicorn app.main:app` or `python -m app.main` from the backend/ folder picks
up backend/.env automatically.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- load backend/.env into the environment -------------------------------- #
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal .env loader so config works even without python-dotenv installed.
    Does not override variables already present in the real environment."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


try:
    from dotenv import load_dotenv

    load_dotenv()  # search cwd and parents
    load_dotenv(_ENV_PATH, override=False)
except ImportError:
    pass
_load_env_file(_ENV_PATH)  # always run the built-in fallback (setdefault is safe)


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Forced provider override; empty => auto-select by available keys.
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "").strip().lower())
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "").strip())

    # Provider keys (presence drives auto-selection).
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    azure_openai_api_key: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY", ""))
    azure_openai_endpoint: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    azure_openai_deployment: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT", ""))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

    # External tool keys. Absent => MCP adapters fall back to offline data.
    google_maps_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_MAPS_API_KEY", ""))
    weather_api_key: str = field(default_factory=lambda: os.getenv("WEATHER_API_KEY", ""))
    fx_api_key: str = field(default_factory=lambda: os.getenv("FX_API_KEY", ""))
    travelpayouts_token: str = field(default_factory=lambda: os.getenv("TRAVELPAYOUTS_TOKEN", ""))

    # Behaviour
    allow_network: bool = field(default_factory=lambda: _bool("ALLOW_NETWORK", True))
    request_timeout_s: float = field(default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT_S", "15")))
    cache_ttl_s: int = field(default_factory=lambda: int(os.getenv("CACHE_TTL_S", "900")))
    max_parallel: int = field(default_factory=lambda: int(os.getenv("MAX_PARALLEL", "6")))


settings = Settings()
