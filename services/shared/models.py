from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel
from enum import Enum

Base = declarative_base()

class ContentStatus(str, Enum):
    SCRAPED = "scraped"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PUBLISHED = "published"
    FAILED = "failed"
    SKIPPED = "skipped"

class ToneType(str, Enum):
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    EDUCATIONAL = "educational"

# Database Models
class ScrapedContent(Base):
    __tablename__ = "scraped_content"
    
    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(255), nullable=False)
    original_url = Column(String(2048), nullable=False, unique=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    published_date = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=func.now())
    content_hash = Column(String(64), nullable=False, unique=True)
    status = Column(String(50), default=ContentStatus.SCRAPED)
    meta = Column(JSON, default={})

class ProcessedContent(Base):
    __tablename__ = "processed_content"
    
    id = Column(Integer, primary_key=True, index=True)
    scraped_content_id = Column(Integer, nullable=False)
    summary = Column(Text, nullable=False)
    seo_title = Column(String(255), nullable=False)
    seo_description = Column(String(500), nullable=False)
    keywords = Column(JSON, default=[])
    hashtags = Column(JSON, default=[])
    category = Column(String(100), nullable=True)
    tone = Column(String(50), default=ToneType.PROFESSIONAL)
    processing_time = Column(Float, nullable=True)
    processed_at = Column(DateTime, default=func.now())
    llm_model = Column(String(100), nullable=True)
    token_usage = Column(JSON, default={})

class PublishedContent(Base):
    __tablename__ = "published_content"
    
    id = Column(Integer, primary_key=True, index=True)
    processed_content_id = Column(Integer, nullable=False)
    platform = Column(String(100), nullable=False)
    external_id = Column(String(255), nullable=True)
    published_url = Column(String(2048), nullable=True)
    published_at = Column(DateTime, default=func.now())
    scheduled_for = Column(DateTime, nullable=True)
    status = Column(String(50), default="published")
    engagement_metrics = Column(JSON, default={})

class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    service = Column(String(100), nullable=False)
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    meta = Column(JSON, default={})
    created_at = Column(DateTime, default=func.now())

# Pydantic Models for API
class ContentItem(BaseModel):
    id: Optional[int] = None
    title: str
    content: Optional[str] = None
    url: str
    source: str
    published_date: Optional[datetime] = None
    status: ContentStatus = ContentStatus.SCRAPED

class ProcessingRequest(BaseModel):
    content_id: int
    tone: ToneType = ToneType.PROFESSIONAL
    target_length: int = 300
    include_seo: bool = True
    custom_prompt: Optional[str] = None

class PublishingRequest(BaseModel):
    content_id: int
    platforms: List[str]
    schedule_time: Optional[datetime] = None
    custom_settings: Dict = {}

class HealthCheck(BaseModel):
    service: str
    status: str
    timestamp: datetime
    version: str
    metrics: Dict = {}