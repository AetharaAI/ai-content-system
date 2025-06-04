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
from datetime import datetime, timedelta
import json
import os

from services.shared.database import get_db, create_tables
from services.shared.models import ScrapedContent, ProcessedContent, ContentStatus
from services.shared.config import settings, DEFAULT_SOURCES
from services.shared.logger import setup_logger
from services.scraper.scrapers import RSScraper, HTMLScraper, JSScraper
from services.scraper.cleaners import TextCleaner, ContentDeduplicator

app = FastAPI(title="Content Scraper Service", version="1.0.0")
logger = setup_logger(__name__)

@app.get("/")
def read_root():
    return {"status": "Content Scraper is running", "version": "2.0.0"}

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

# Fixed startup event
@app.on_event("startup")
async def startup_event():
    try:
        create_tables()
        logger.info("Scraper service started")
        # Start periodic scraping as background task
        asyncio.create_task(periodic_scraping_task())
    except Exception as e:
        logger.error(f"Startup error: {e}")

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

# Fixed periodic scraping function
async def periodic_scraping_task():
    """Background task that runs scraping periodically"""
    logger.info("Starting periodic scraping task")
    
    while True:
        try:
            # Use the context manager properly
            with get_db() as db:
                logger.info("Running periodic scrape")
                results = await orchestrator.scrape_all_sources(db)
                logger.info(f"Periodic scrape results: {results}")
            
            # Wait for next interval (4 hours by default)
            await asyncio.sleep(settings.DEFAULT_PUBLISH_INTERVAL * 3600)
            
        except Exception as e:
            logger.error(f"Periodic scraping error: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes on error

# WordPress Widget Endpoints
@app.get("/widgets/wordpress-articles", response_class=HTMLResponse)
async def wordpress_articles_widget(
    limit: int = 5,
    style: str = "modern",
    category: str = None,
    db: Session = Depends(get_db)
):
    """Generate WordPress-compatible article widget"""
    
    try:
        # Query scraped content directly since ProcessedContent might not exist yet
        query = db.query(ScrapedContent).order_by(desc(ScrapedContent.scraped_at))
        
        if category:
            # Simple category filtering based on source name or title
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
                'summary': (item.content[:300] + "...") if item.content and len(item.content) > 300 else (item.content or "No summary available"),
                'description': item.title,  # Use title as description for now
                'url': item.original_url,
                'date': item.scraped_at.strftime('%B %d, %Y'),
                'time_ago': get_time_ago(item.scraped_at),
                'category': item.source_name,
                'hashtags': [],  # Empty for now
                'source': item.source_name,
                'reading_time': estimate_reading_time(item.content or item.title)
            })
        
        # Modern card style template
        if style == "modern":
            template = """
            <div class="ai-central-articles-modern" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px;">
                <style>
                    .ai-article-card {
                        background: #fff;
                        border-radius: 12px;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                        margin: 20px 0;
                        padding: 24px;
                        transition: transform 0.2s, box-shadow 0.2s;
                        border-left: 4px solid #0073aa;
                    }
                    .ai-article-card:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 8px 15px rgba(0, 0, 0, 0.15);
                    }
                    .ai-article-title {
                        font-size: 20px;
                        font-weight: 600;
                        color: #1a1a1a;
                        text-decoration: none;
                        line-height: 1.4;
                        margin-bottom: 12px;
                        display: block;
                    }
                    .ai-article-title:hover {
                        color: #0073aa;
                    }
                    .ai-article-meta {
                        display: flex;
                        align-items: center;
                        gap: 15px;
                        margin-bottom: 15px;
                        font-size: 14px;
                        color: #666;
                    }
                    .ai-article-category {
                        background: #e3f2fd;
                        color: #1976d2;
                        padding: 4px 12px;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: 500;
                    }
                    .ai-article-summary {
                        color: #444;
                        line-height: 1.6;
                        margin-bottom: 15px;
                        font-size: 15px;
                    }
                    .ai-article-footer {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-top: 15px;
                        padding-top: 15px;
                        border-top: 1px solid #eee;
                        font-size: 13px;
                        color: #888;
                    }
                    @media (max-width: 768px) {
                        .ai-article-card { padding: 16px; margin: 15px 0; }
                        .ai-article-title { font-size: 18px; }
                        .ai-article-meta { flex-direction: column; align-items: flex-start; gap: 8px; }
                    }
                </style>
                
                {% for article in articles %}
                <div class="ai-article-card">
                    <a href="{{ article.url }}" target="_blank" class="ai-article-title">
                        {{ article.title }}
                    </a>
                    
                    <div class="ai-article-meta">
                        <span class="ai-article-category">{{ article.category }}</span>
                        <span>📅 {{ article.time_ago }}</span>
                        <span>⏱️ {{ article.reading_time }} min read</span>
                    </div>
                    
                    <div class="ai-article-summary">
                        {{ article.summary }}
                    </div>
                    
                    <div class="ai-article-footer">
                        <span>Published {{ article.date }}</span>
                        <a href="{{ article.url }}" target="_blank" style="color: #0073aa; text-decoration: none; font-weight: 500;">
                            Read Full Article →
                        </a>
                    </div>
                </div>
                {% endfor %}
            </div>
            """
        else:  # Simple list style
            template = """
            <div class="ai-central-articles-list" style="font-family: Arial, sans-serif;">
                {% for article in articles %}
                <div style="border-bottom: 1px solid #ddd; padding: 20px 0;">
                    <h3 style="margin: 0 0 10px 0;">
                        <a href="{{ article.url }}" target="_blank" style="color: #0073aa; text-decoration: none;">
                            {{ article.title }}
                        </a>
                    </h3>
                    <p style="color: #666; margin: 0 0 10px 0; line-height: 1.5;">
                        {{ article.summary }}
                    </p>
                    <div style="font-size: 14px; color: #999;">
                        <span>{{ article.date }}</span> • 
                        <span>{{ article.category }}</span>
                    </div>
                </div>
                {% endfor %}
            </div>
            """
        
        html_template = Template(template)
        html_content = html_template.render(articles=articles)
        
        return HTMLResponse(content=html_content)
    
    except Exception as e:
        logger.error(f"Error in wordpress_articles_widget: {e}")
        return HTMLResponse(content=f"<div>Error loading articles: {str(e)}</div>", status_code=500)

@app.get("/api/wordpress-feed")
async def wordpress_feed(
    limit: int = 10,
    category: str = None,
    db: Session = Depends(get_db)
):
    """JSON API for WordPress AJAX calls"""
    
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

# Simple widget for immediate testing
@app.get("/widgets/simple-articles", response_class=HTMLResponse)
async def simple_articles_widget(limit: int = 5, db: Session = Depends(get_db)):
    """Simple article widget for testing"""
    try:
        articles = db.query(ScrapedContent).order_by(desc(ScrapedContent.scraped_at)).limit(limit).all()

        html = """
        <div style="font-family: Arial, sans-serif; max-width: 800px;">
            <h3 style="color: #0073aa; border-bottom: 2px solid #0073aa; padding-bottom: 10px;">
                🤖 Latest AI News
            </h3>
        """
        
        for article in articles:
            html += f"""
            <div style="border: 1px solid #ddd; margin: 15px 0; padding: 15px; border-radius: 8px;">
                <h4 style="margin: 0 0 10px 0;">
                    <a href="{article.original_url}" target="_blank" style="color: #0073aa; text-decoration: none;">
                        {article.title}
                    </a>
                </h4>
                <p style="color: #666; margin: 0 0 10px 0; font-size: 14px;">
                    Source: {article.source_name} • 
                    {article.scraped_at.strftime('%B %d, %Y')}
                </p>
                {f'<p style="color: #444; line-height: 1.5;">{article.content[:200]}...</p>' if article.content else ''}
            </div>
            """
        
        html += "</div>"
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error in simple_articles_widget: {e}")
        return HTMLResponse(content=f"<div>Error loading articles: {str(e)}</div>", status_code=500)

# Helper functions
def get_time_ago(date):
    """Get human-readable time ago"""
    now = datetime.utcnow()
    diff = now - date
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"

def estimate_reading_time(text):
    """Estimate reading time in minutes"""
    if not text:
        return 1
    words = len(text.split())
    return max(1, round(words / 200))  # Average 200 words per minute

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
        log_level=settings.LOG_LEVEL.lower()
    )