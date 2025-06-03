import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from dataclasses import dataclass

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:Gmccmg#2024@db.mlnzppqqakqvxdopnyhl.supabase.co:5432/postgres"
    REDIS_URL: str = "redis://localhost:6379"
    
    # LLM APIs
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # Publishers
    FIREBASE_CREDENTIALS: Optional[str] = None
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    NOTION_TOKEN: Optional[str] = None
    WORDPRESS_API_URL: Optional[str] = None
    WORDPRESS_TOKEN: Optional[str] = None
    
    # Service URLs
    SCRAPER_URL: str = "http://localhost:8001"
    SUMMARIZER_URL: str = "http://localhost:8002"
    PUBLISHER_URL: str = "http://localhost:8003"
    DASHBOARD_URL: str = "http://localhost:8004"
    
    # App Config
    MAX_ARTICLES_PER_SCRAPE: int = 50
    CONTENT_PROCESSING_BATCH_SIZE: int = 10
    DEFAULT_PUBLISH_INTERVAL: int = 4  # hours
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"

@dataclass
class ScrapingSource:
    name: str
    url: str
    scraper_type: str  # 'rss', 'html', 'js'
    selectors: dict = None
    enabled: bool = True
    interval_hours: int = 4

# Default scraping sources
DEFAULT_SOURCES = [
    ScrapingSource("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "rss"),
    ScrapingSource("VentureBeat AI", "https://venturebeat.com/ai/feed/", "rss"),
    ScrapingSource("Google News AI", "https://news.google.com/rss/search?q=artificial+intelligence", "rss"),
    ScrapingSource("Hacker News", "https://news.ycombinator.com/", "html", {
        "title": ".titleline > a",
        "link": ".titleline > a",
        "score": ".score"
    }),
    ScrapingSource("Reddit r/MachineLearning", "https://www.reddit.com/r/MachineLearning.json", "html")
]

settings = Settings()