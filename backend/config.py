from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_path: str = os.getenv("DATABASE_PATH", "agentflow.db")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    llm_mock: bool = os.getenv("LLM_MOCK", "true").lower() in {"1", "true", "yes"}
    quality_threshold: int = int(os.getenv("QUALITY_THRESHOLD", "80"))
    max_loop_count: int = int(os.getenv("MAX_LOOP_COUNT", "3"))
    external_search_enabled: bool = os.getenv("EXTERNAL_SEARCH_ENABLED", "true").lower() in {"1", "true", "yes"}
    openalex_api_key: str = os.getenv("OPENALEX_API_KEY", "")
    crossref_mailto: str = os.getenv("CROSSREF_MAILTO", "")
    brave_search_api_key: str = os.getenv("BRAVE_SEARCH_API_KEY", "")
    external_search_limit: int = int(os.getenv("EXTERNAL_SEARCH_LIMIT", "4"))


settings = Settings()

