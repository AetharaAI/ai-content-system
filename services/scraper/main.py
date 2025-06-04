from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from jinja2 import Template
import asyncio
import uvicorn
from typing import List, Dict
import logging
import os
from datetime import datetime, timedelta
import json

from services.shared.database import get_db, create_tables, SessionLocal
from services.shared.models import ScrapedContent, ProcessedContent, ContentStatus
from services.shared.config import settings, DEFAULT_SOURCES
from services.shared.logger import setup_logger
from services.scraper.scrapers import RSScraper, HTMLScraper, JSScraper
from services.scraper.cleaners import TextCleaner, ContentDeduplicator

app = FastAPI(title="Content Scraper Service", version="1.0.0")
logger = setup_logger(__name__)

@app.get("/")
def read_root():
    return {
        "status": "Content Scraper is running", 
        "version": "2.0.0",
        "service": "AI Content Automation",
        "endpoints": ["/health", "/scrape", "/scrape/status", "/widgets/simple-articles"]
    }

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

# Fixed sources - remove problematic ones for now
WORKING_SOURCES = [
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "scraper_type": "rss",
        "enabled": True
    },
    {
        "name": "Google News AI", 
        "url": "https://news.google.com/rss/search?q=artificial+intelligence",
        "scraper_type": "rss", 
        "enabled": True
    }
]

class ScrapingOrchestrator:
    def __init__(self):
        self.scrapers = {
            'rss': RSScraper(),
            'html': HTMLScraper(),
            'js': JSScraper()
        }
        # Use working sources only
        from dataclasses import dataclass
        
        @dataclass
        class SimpleSource:
            name: str
            url: str
            scraper_type: str
            enabled: bool = True
            selectors: dict = None
        
        self.sources = [SimpleSource(**source) for source in WORKING_SOURCES]
    
    async def scrape_all_sources(self) -> Dict:
        """Scrape all configured sources - fixed for Render"""
        results = {
            'success': 0,
            'failed': 0,
            'duplicates': 0,
            'total_processed': 0
        }
        
        # Create a new database session for this operation
        db = SessionLocal()
        
        try:
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
            
        except Exception as e:
            logger.error(f"Error in scrape_all_sources: {e}")
            return results
        finally:
            db.close()
    
    async def scrape_source(self, source, db: Session) -> Dict:
        """Scrape a single source with better error handling"""
        try:
            logger.info(f"Starting scrape for {source.name}")
            
            scraper = self.scrapers.get(source.scraper_type)
            if not scraper:
                raise ValueError(f"Unknown scraper type: {source.scraper_type}")
            
            # Scrape content
            raw_articles = await scraper.scrape(source.url, getattr(source, 'selectors', None))
            
            processed_count = 0
            duplicate_count = 0
            
            for article in raw_articles:
                try:
                    # Clean content
                    cleaned_article = text_cleaner.clean_article(article)
                    
                    # Check for duplicates using URL
                    existing = db.query(ScrapedContent).filter(
                        ScrapedContent.original_url == cleaned_article['url']
                    ).first()
                    
                    if existing:
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
                            'source_config': source.__dict__ if hasattr(source, '__dict__') else {}
                        }
                    )
                    
                    db.add(content)
                    processed_count += 1
                    
                    # Commit after each article to avoid batch constraint violations
                    try:
                        db.commit()
                    except Exception as commit_error:
                        db.rollback()
                        logger.warning(f"Failed to save article (likely duplicate): {commit_error}")
                        duplicate_count += 1
                    
                    if processed_count >= settings.MAX_ARTICLES_PER_SCRAPE:
                        break
                        
                except Exception as article_error:
                    logger.warning(f"Error processing article: {article_error}")
                    continue
            
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

# Fixed startup event
@app.on_event("startup")
async def startup_event():
    try:
        create_tables()
        logger.info("Scraper service started successfully")
        logger.info("Starting background scraping task")
        # Start periodic scraping as background task
        asyncio.create_task(periodic_scraping_task())
    except Exception as e:
        logger.error(f"Startup error: {e}")

@app.post("/scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """Manually trigger scraping"""
    background_tasks.add_task(orchestrator.scrape_all_sources)
    return {"message": "Scraping started", "status": "processing"}

@app.get("/scrape/status")
async def get_scrape_status():
    """Get scraping statistics - fixed for Render"""
    db = SessionLocal()
    try:
        total_scraped = db.query(func.count(ScrapedContent.id)).scalar() or 0
        today_scraped = db.query(func.count(ScrapedContent.id)).filter(
            ScrapedContent.scraped_at >= datetime.utcnow().date()
        ).scalar() or 0
        
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
    except Exception as e:
        logger.error(f"Error in get_scrape_status: {e}")
        return {
            "total_articles": 0,
            "today_articles": 0,
            "by_source": [],
            "last_updated": datetime.utcnow(),
            "error": str(e)
        }
    finally:
        db.close()

@app.get("/health")
async def health_check():
    return {
        "service": "scraper",
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "version": "2.0.0",
        "port": os.environ.get("PORT", "8001")
    }

# Fixed periodic scraping function
async def periodic_scraping_task():
    """Background task that runs scraping periodically"""
    logger.info("Periodic scraping task started")
    
    # Wait a bit before starting first scrape
    await asyncio.sleep(30)
    
    while True:
        try:
            logger.info("Running periodic scrape")
            results = await orchestrator.scrape_all_sources()
            logger.info(f"Periodic scrape results: {results}")
            
            # Wait for next interval (4 hours by default, but shorter for testing)
            wait_time = min(settings.DEFAULT_PUBLISH_INTERVAL * 3600, 1800)  # Max 30 minutes
            logger.info(f"Waiting {wait_time} seconds until next scrape")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"Periodic scraping error: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes on error

# Fixed simple widget
@app.get("/widgets/simple-articles", response_class=HTMLResponse)
async def simple_articles_widget(limit: int = 5):
    """Simple article widget for testing - fixed for Render"""
    db = SessionLocal()
    try:
        articles = db.query(ScrapedContent).order_by(desc(ScrapedContent.scraped_at)).limit(limit).all()

        if not articles:
            return HTMLResponse(content="""
                <div style="font-family: Arial, sans-serif; padding: 20px; text-align: center;">
                    <h3 style="color: #0073aa;">🤖 AI Content System</h3>
                    <p>No articles available yet. The system is starting up...</p>
                    <p><small>Check back in a few minutes!</small></p>
                </div>
            """)

        html = """
        <div style="font-family: Arial, sans-serif; max-width: 800px;">
            <h3 style="color: #0073aa; border-bottom: 2px solid #0073aa; padding-bottom: 10px;">
                🤖 Latest AI News
            </h3>
        """
        
        for article in articles:
            summary = ""
            if article.content:
                summary = f'<p style="color: #444; line-height: 1.5;">{article.content[:200]}{"..." if len(article.content) > 200 else ""}</p>'
            
            html += f"""
            <div style="border: 1px solid #ddd; margin: 15px 0; padding: 15px; border-radius: 8px; background: #fff;">
                <h4 style="margin: 0 0 10px 0;">
                    <a href="{article.original_url}" target="_blank" style="color: #0073aa; text-decoration: none;">
                        {article.title}
                    </a>
                </h4>
                <p style="color: #666; margin: 0 0 10px 0; font-size: 14px;">
                    📰 {article.source_name} • 
                    📅 {article.scraped_at.strftime('%B %d, %Y at %I:%M %p')}
                </p>
                {summary}
                <div style="margin-top: 10px;">
                    <a href="{article.original_url}" target="_blank" 
                       style="background: #0073aa; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-size: 14px;">
                        Read Full Article →
                    </a>
                </div>
            </div>
            """
        
        html += f"""
            <div style="text-align: center; margin-top: 30px; padding: 20px; background: #f9f9f9; border-radius: 8px;">
                <p style="margin: 0; color: #666;">
                    ✨ Powered by AI Content Automation System<br>
                    <small>Last updated: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}</small>
                </p>
            </div>
        </div>
        """
        
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error in simple_articles_widget: {e}")
        return HTMLResponse(content=f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; color: #d32f2f; background: #ffebee; border-radius: 8px;">
                <h3>⚠️ Error Loading Articles</h3>
                <p>There was an issue loading the content. Please try again later.</p>
                <p><small>Error: {str(e)}</small></p>
            </div>
        """, status_code=500)
    finally:
        db.close()

# API endpoint for WordPress
@app.get("/api/wordpress-feed")
async def wordpress_feed(limit: int = 10, category: str = None):
    """JSON API for WordPress AJAX calls - fixed for Render"""
    db = SessionLocal()
    try:
        query = db.query(ScrapedContent).order_by(desc(ScrapedContent.scraped_at))
        
        if category:
            query = query.filter(
                ScrapedContent.source_name.ilike(f"%{category}%") |
                ScrapedContent.title.ilike(f"%{category}%")
            )
        
        content = query.limit(limit).all()
        
        articles = []
        for item in content:
            articles.append({
                'id': item.id,
                'title': item.title,
                'summary': item.content or "No content available",
                'description': item.title,
                'url': item.original_url,
                'date': item.scraped_at.isoformat(),
                'category': item.source_name,
                'hashtags': [],
                'keywords': [],
                'source': item.source_name
            })
        
        return {
            'status': 'success',
            'count': len(articles),
            'articles': articles,
            'last_updated': datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in wordpress_feed: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'articles': [],
            'count': 0
        }
    finally:
        db.close()

# Test endpoint to trigger immediate scrape
@app.get("/test/scrape-now")
async def test_scrape_now():
    """Test endpoint to trigger immediate scraping"""
    try:
        results = await orchestrator.scrape_all_sources()
        return {
            "message": "Scraping completed",
            "results": results,
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": "Scraping failed",
            "timestamp": datetime.utcnow()
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,  # Disable reload for production
        log_level="info"
    )