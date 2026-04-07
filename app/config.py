"""Application configuration via environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    app_db_url: str = "sqlite+aiosqlite:///./app.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index: str = "doc-rag-index"

    # LiteLLM / Azure AI Foundry
    litellm_base_url: str = ""
    litellm_api_key: str = ""
    litellm_chat_model: str = "azure/claude-sonnet-4"
    litellm_embed_model: str = "azure/text-embedding-3-large"

    # Embeddings
    embedding_dimensions: int = 3072

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Upload limits
    max_upload_mb: int = 50


settings = Settings()
