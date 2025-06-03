# Add this to your services/dashboard/main.py

from fastapi.responses import HTMLResponse, Response
from jinja2 import Template
import json

# WordPress Widget Endpoints
@app.get("/widgets/wordpress-articles", response_class=HTMLResponse)
async def wordpress_articles_widget(
    limit: int = 5,
    style: str = "modern",
    category: str = None,
    db: Session = Depends(get_db)
):
    """Generate WordPress-compatible article widget"""
    
    query = db.query(ProcessedContent).join(ScrapedContent).order_by(
        desc(ProcessedContent.processed_at)
    )
    
    if category:
        query = query.filter(ProcessedContent.category.ilike(f"%{category}%"))
    
    content = query.limit(limit).all()
    
    articles = []
    for item in content:
        scraped = db.query(ScrapedContent).filter(
            ScrapedContent.id == item.scraped_content_id
        ).first()
        
        articles.append({
            'id': item.id,
            'title': item.seo_title,
            'summary': item.summary[:300] + "..." if len(item.summary) > 300 else item.summary,
            'description': item.seo_description,
            'url': scraped.original_url,
            'date': item.processed_at.strftime('%B %d, %Y'),
            'time_ago': get_time_ago(item.processed_at),
            'category': item.category or 'AI News',
            'hashtags': item.hashtags[:4],  # First 4 hashtags
            'source': scraped.source_name,
            'reading_time': estimate_reading_time(item.summary)
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
                .ai-article-hashtags {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 8px;
                    margin-top: 15px;
                }
                .ai-hashtag {
                    background: #f5f5f5;
                    color: #0073aa;
                    padding: 4px 10px;
                    border-radius: 15px;
                    font-size: 12px;
                    text-decoration: none;
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
                    <span>📰 {{ article.source }}</span>
                </div>
                
                <div class="ai-article-summary">
                    {{ article.summary }}
                </div>
                
                {% if article.hashtags %}
                <div class="ai-article-hashtags">
                    {% for hashtag in article.hashtags %}
                    <span class="ai-hashtag">{{ hashtag }}</span>
                    {% endfor %}
                </div>
                {% endif %}
                
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
                    {{ article.description }}
                </p>
                <div style="font-size: 14px; color: #999;">
                    <span>{{ article.date }}</span> • 
                    <span>{{ article.category }}</span> • 
                    <span>{{ article.source }}</span>
                </div>
            </div>
            {% endfor %}
        </div>
        """
    
    html_template = Template(template)
    html_content = html_template.render(articles=articles)
    
    return HTMLResponse(content=html_content)

@app.get("/api/wordpress-feed")
async def wordpress_feed(
    limit: int = 10,
    category: str = None,
    db: Session = Depends(get_db)
):
    """JSON API for WordPress AJAX calls"""
    
    query = db.query(ProcessedContent).join(ScrapedContent).order_by(
        desc(ProcessedContent.processed_at)
    )
    
    if category:
        query = query.filter(ProcessedContent.category.ilike(f"%{category}%"))
    
    content = query.limit(limit).all()
    
    articles = []
    for item in content:
        scraped = db.query(ScrapedContent).filter(
            ScrapedContent.id == item.scraped_content_id
        ).first()
        
        articles.append({
            'id': item.id,
            'title': item.seo_title,
            'summary': item.summary,
            'description': item.seo_description,
            'url': scraped.original_url,
            'date': item.processed_at.isoformat(),
            'category': item.category,
            'hashtags': item.hashtags,
            'keywords': item.keywords,
            'source': scraped.source_name
        })
    
    return {
        'status': 'success',
        'count': len(articles),
        'articles': articles,
        'last_updated': datetime.utcnow().isoformat()
    }

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
    words = len(text.split())
    return max(1, round(words / 200))  # Average 200 words per minute