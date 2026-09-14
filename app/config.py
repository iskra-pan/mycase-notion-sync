"""
Central configuration, loaded from environment variables (.env locally,
Cloud Run env vars / Secret Manager in production).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- MyCase OAuth app credentials (given to you by MyCase support) ---
    mycase_client_id: str = ""
    mycase_client_secret: str = ""
    # Must exactly match what MyCase has on file for this client_id.
    mycase_redirect_uri: str = "http://localhost:8080/auth/mycase/callback"

    mycase_auth_base: str = "https://auth.mycase.com"
    # TODO CONFIRM: the actual data-API host - auth.mycase.com is documented
    # as the OAuth host only. Leave blank until confirmed; mycase_client.py
    # will raise a clear error rather than silently calling the wrong host.
    mycase_api_base: str = ""

    # --- Shared secret for calling the internal token-refresh endpoint
    # (e.g. from Cloud Scheduler). Not the same as an OAuth secret. ---
    internal_task_secret: str = "change-me"

    # --- Google Cloud project (used for Firestore token storage) ---
    gcp_project_id: str = ""

    # --- Notion (internal integration token, set up in phase 2) ---
    notion_token: str = ""
    notion_database_id: str = ""


settings = Settings()
