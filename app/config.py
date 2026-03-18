import os
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel
from dotenv import load_dotenv


load_dotenv()


class Settings(BaseModel):
    app_name: str = "ZynthClaw AI Evaluation Agent"
    github_token: Optional[str] = os.getenv("GITHUB_TOKEN")
    github_api_base: str = "https://api.github.com"
    github_search_page_size: int = 50  # per-page repositories when crawling topics
    github_max_pages: int = 1  # can be increased if you want more than top 50
    evaluation_max_repos: int = 50  # top N repositories to evaluate
    smtp_host: Optional[str] = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: Optional[str] = os.getenv("SMTP_USERNAME")
    smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD")
    smtp_from_email: Optional[str] = os.getenv("SMTP_FROM_EMAIL")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}
    telegram_bot_username: Optional[str] = os.getenv("TELEGRAM_BOT_USERNAME")


@lru_cache
def get_settings() -> Settings:
    return Settings()

