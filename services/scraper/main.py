from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import asyncio
import uvicorn
from typing import List, Dict
import logging
from datetime import datetime, timedelta

from ..shared.database import get_db, create_tables
from ..shared.models import ScrapedContent, ContentStatus
from ..shared.config import settings, DEFAULT_SOURCES
from ..shared.logger import setup_logger
from .scrapers import RSScraper, HTMLScraper, JSScraper
from .cleaners import TextCleaner, ContentDeduplicator

app = FastAPI(title="Content Scraper Service", version="1.0.0")
logger = setup_logger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
text_cleaner = TextCleaner()
deduplicator = ContentDeduplicator()

class ScrapingOrchestrator:
    def __init__(self):
        self.scrapers = {
            'rss': RSScraper(),
            'html': HTMLScraper(),
            'js': JSScraper()
        }
        self.sources = DEFAULT_SOURCES
    
    async def scrape_all_sources(self, db: Session) -> Dict:
        """Scrape all configured sources"""
        results = {
            'success': 0,
            'failed': 0,
            'duplicates': 0,
            'total_processed': 0
        }
        
        tasks = []
        for source in self.sources:
            if source.enabled:
                task = self.scrape_source(source, db)
                tasks.append(task)
        
        source_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in source_results:
            if isinstance(result, Exception):
                logger.error(f"Scraping task failed: {result}")
                results['failed'] += 1
            else:
                results['success'] += result.get('scraped', 0)
                results['duplicates'] += result.get('duplicates', 0)
                results['total_processed'] += result.get('processed', 0)
        
        return results
    
    async def scrape_source(self, source, db: Session) -> Dict:
        """Scrape a single source"""
        try:
            logger.info(f"Starting scrape for {source.name}")
            
            scraper = self.scrapers.get(source.scraper_type)
            if not scraper:
                raise ValueError(f"Unknown scraper type: {source.scraper_type}")
            
            # Scrape content
            raw_articles = await scraper.scrape(source.url, source.selectors)
            
            processed_count = 0
            duplicate_count = 0
            
            for article in raw_articles:
                # Clean content
                cleaned_article = text_cleaner.clean_article(article)
                
                # Check for duplicates
                if deduplicator.is_duplicate(cleaned_article, db):
                    duplicate_count += 1
                    continue
                
                # Save to database
                content = ScrapedContent(
                    source_name=source.name,
                    original_url=cleaned_article['url'],
                    title=cleaned_article['title'],
                    content=cleaned_article.get('content', ''),
                    author=cleaned_article.get('author', ''),
                    published_date=cleaned_article.get('published_date'),
                    content_hash=deduplicator.generate_hash(cleaned_article),
                    status=ContentStatus.SCRAPED,
                    metadata={
                        'scraper_type': source.scraper_type,
                        'source_config': source.__dict__
                    }
                )
                
                db.add(content)
                processed_count += 1
                
                if processed_count >= settings.MAX_ARTICLES_PER_SCRAPE:
                    break
            
            db.commit()
            
            logger.info(f"Completed scraping {source.name}: {processed_count} new articles")
            
            return {
                'scraped': processed_count,
                'duplicates': duplicate_count,
                'processed': processed_count + duplicate_count
            }
            
        except Exception as e:
            logger.error(f"Error scraping {source.name}: {e}")
            db.rollback()
            return {'scraped': 0, 'duplicates': 0, 'processed': 0}

orchestrator = ScrapingOrchestrator()

@app.on_event("startup")
async def startup_event():
    create_tables()
    logger.info("Scraper service started")

@app.post("/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Manually trigger scraping"""
    background_tasks.add_task(orchestrator.scrape_all_sources, db)
    return {"message": "Scraping started", "status": "processing"}

@app.get("/scrape/status")
async def get_scrape_status(db: Session = Depends(get_db)):
    """Get scraping statistics"""
    from sqlalchemy import func
    
    total_scraped = db.query(func.count(ScrapedContent.id)).scalar()
    today_scraped = db.query(func.count(ScrapedContent.id)).filter(
        ScrapedContent.scraped_at >= datetime.utcnow().date()
    ).scalar()
    
    by_source = db.query(
        ScrapedContent.source_name,
        func.count(ScrapedContent.id).label('count')
    ).group_by(ScrapedContent.source_name).all()
    
    return {
        "total_articles": total_scraped,
        "today_articles": today_scraped,
        "by_source": [{"source": s[0], "count": s[1]} for s in by_source],
        "last_updated": datetime.utcnow()
    }

@app.get("/health")
async def health_check():
    return {
        "service": "scraper",
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "version": "1.0.0"
    }

# Background task for periodic scraping
async def periodic_scraping():
    """Background task that runs scraping periodically"""
    while True:
        try:
            with get_db() as db:
                await orchestrator.scrape_all_sources(db)
            
            # Wait for next interval
            await asyncio.sleep(settings.DEFAULT_PUBLISH_INTERVAL * 3600)
            
        except Exception as e:
            logger.error(f"Periodic scraping error: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes on error

@app.on_event("startup")
async def start_periodic_scraping():
    asyncio.create_task(periodic_scraping())

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )