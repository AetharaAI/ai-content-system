from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import redis
from contextlib import contextmanager
from .config import settings
from .models import Base
import logging

logger = logging.getLogger(__name__)

# PostgreSQL Database
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=StaticPool,
    pool_pre_ping=True,
    echo=settings.LOG_LEVEL == "DEBUG"
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redis Cache
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")

@contextmanager
def get_db() -> Session:
    """Database session context manager"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

class CacheManager:
    """Redis cache manager"""
    
    def __init__(self):
        self.redis = redis_client
        self.default_ttl = 3600  # 1 hour
    
    def get(self, key: str):
        try:
            return self.redis.get(key)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: str, ttl: int = None):
        try:
            ttl = ttl or self.default_ttl
            return self.redis.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str):
        try:
            return self.redis.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        try:
            return bool(self.redis.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False

cache = CacheManager()