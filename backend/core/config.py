"""
PULSE DevOps Agent — Core Configuration
All environment variables are loaded here via pydantic-settings.

WHY pydantic-settings?
  - Automatic type coercion (string "true" → bool True)
  - Validates required fields at startup, not at runtime
  - Works with .env files automatically
  - One source of truth for all config
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All PULSE configuration loaded from environment variables / .env file.
    Add a new config here whenever you add a new feature.
    """

    model_config = SettingsConfigDict(
        env_file=".env",          # Load from .env file
        env_file_encoding="utf-8",
        case_sensitive=False,     # OPENAI_API_KEY or openai_api_key both work
        extra="ignore",           # Ignore unknown env vars (safe)
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "PULSE DevOps Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite is perfect for local development — no setup needed
    DATABASE_URL: str = "sqlite+aiosqlite:///./pulse_agent.db"

    # ── AI / LLM ──────────────────────────────────────────────────────────────
    # OpenAI is primary. Gemini is fallback. Neither = offline mode.
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # Which model to use for fix generation
    LLM_MODEL: str = "gpt-4o-mini"          # Cheap + capable. Use gpt-4o for better fixes.
    LLM_TEMPERATURE: float = 0.1             # Low temp = more deterministic fixes
    GEMINI_MODEL: str = "gemini-1.5-flash"   # Free fallback model

    # ── GitHub ────────────────────────────────────────────────────────────────
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_USERNAME: Optional[str] = None
    GITHUB_EMAIL: str = "pulse-agent@devops.local"

    # GitHub OAuth (optional — for user-scoped operations)
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None

    # ── Vector Memory (Phase 4) ───────────────────────────────────────────────
    VECTOR_DB_PATH: str = "./pulse_memory"   # Where ChromaDB stores patterns
    VECTOR_DB_TYPE: str = "chromadb"

    # ── Agent Behavior ────────────────────────────────────────────────────────
    MAX_SCAN_FILES: int = 50              # Max files to scan per run
    MAX_FIX_ATTEMPTS: int = 5            # Max retry iterations for CI
    RETRY_DELAY_SECONDS: int = 30        # Wait between CI checks
    SANDBOX_TIMEOUT: int = 60            # Subprocess timeout in seconds

    # ── Offline Mode ──────────────────────────────────────────────────────────
    # If True, uses rule-based fixes only — no API calls needed
    OFFLINE_MODE: bool = False

    # ── Scoring Thresholds ────────────────────────────────────────────────────
    # Repository health score thresholds (0-100)
    HEALTH_SCORE_CRITICAL: int = 40      # Below this = critical
    HEALTH_SCORE_WARNING: int = 70       # Below this = needs attention

    @property
    def llm_available(self) -> bool:
        """Returns True if any LLM API key is configured"""
        return bool(self.OPENAI_API_KEY or self.GEMINI_API_KEY)

    @property
    def active_llm(self) -> str:
        """Returns which LLM will be used"""
        if self.OPENAI_API_KEY:
            return "openai"
        if self.GEMINI_API_KEY:
            return "gemini"
        return "offline"


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached settings instance.
    lru_cache ensures we only read the .env file ONCE per process.
    Call this anywhere with: from core.config import get_settings; settings = get_settings()
    """
    return Settings()


# Convenience: module-level settings instance
# Import directly: from core.config import settings
settings = get_settings()
