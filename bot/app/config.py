import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _optional_secret(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip() and value.strip().lower() != "change_me":
            return value.strip()
    return None


def _required_secret(*names: str) -> str:
    value = _optional_secret(*names)
    if value is not None:
        return value
    joined = ", ".join(names)
    raise RuntimeError(f"Missing required secret env var. Set one of: {joined}")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    llm_provider: str
    openai_api_key: str | None
    openai_model: str
    database_url: str
    jpy_to_rub_rate: float
    bot_results_limit: int
    bot_session_ttl_seconds: int
    photo_timeout_seconds: float
    scrape_trigger_debounce_seconds: int
    bot_max_pending_scrape_requests: int

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none"


def build_database_url() -> str:
    postgres_user = _env("POSTGRES_USER", "car_user")
    postgres_password = _env("POSTGRES_PASSWORD", "car_pass")
    postgres_host = _env("POSTGRES_HOST", "db")
    postgres_port = _env("POSTGRES_PORT", "5432")
    postgres_db = _env("POSTGRES_DB", "car_research")
    return f"postgresql+psycopg2://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"


_llm_provider = _env("LLM_PROVIDER", "openai").strip().lower()
_openai_key = _optional_secret("OPENAI_API_KEY", "LLM_API_KEY")
if _llm_provider == "openai" and _openai_key is None:
    # Keep bot functional with fallback parser even without OpenAI key.
    _llm_provider = "none"


SETTINGS = Settings(
    telegram_bot_token=_required_secret("TELEGRAM_BOT_TOKEN"),
    llm_provider=_llm_provider,
    openai_api_key=_openai_key,
    openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
    database_url=build_database_url(),
    jpy_to_rub_rate=float(_env("JPY_TO_RUB_RATE", "0.62")),
    bot_results_limit=int(_env("BOT_RESULTS_LIMIT", "20")),
    bot_session_ttl_seconds=int(_env("BOT_SESSION_TTL_SECONDS", "1800")),
    photo_timeout_seconds=float(_env("BOT_PHOTO_TIMEOUT_SECONDS", "10")),
    scrape_trigger_debounce_seconds=int(_env("BOT_SCRAPE_TRIGGER_DEBOUNCE_SECONDS", "120")),
    bot_max_pending_scrape_requests=int(_env("BOT_MAX_PENDING_SCRAPE_REQUESTS", "50")),
)
