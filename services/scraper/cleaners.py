import hashlib
import re
from typing import Dict, List
from sqlalchemy.orm import Session
from ..shared.models import ScrapedContent
import logging

logger = logging.getLogger(__name__)

class TextCleaner:
    """Clean and normalize scraped text content"""
    
    def clean_article(self, article: Dict) -> Dict:
        """Clean article content"""
        cleaned = article.copy()
        
        # Clean title
        if 'title' in cleaned:
            cleaned['title'] = self._clean_text(cleaned['title'])
        
        # Clean content
        if 'content' in cleaned:
            cleaned['content'] = self._clean_text(cleaned['content'])
        
        # Clean author
        if 'author' in cleaned:
            cleaned['author'] = self._clean_text(cleaned['author'])
        
        return cleaned
    
    def _clean_text(self, text: str) -> str:
        """Clean individual text field"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove common junk patterns
        text = re.sub(r'\[.*?\]', '', text)  # Remove [brackets]
        text = re.sub(r'\(Advertisement\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Continue reading.*', '', text, flags=re.IGNORECASE)
        
        # Remove URLs from text
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        return text.strip()

class ContentDeduplicator:
    """Handle content deduplication"""
    
    def generate_hash(self, article: Dict) -> str:
        """Generate content hash for deduplication"""
        content_string = f"{article.get('title', '')}{article.get('content', '')}"
        return hashlib.sha256(content_string.encode()).hexdigest()
    
    def is_duplicate(self, article: Dict, db: Session) -> bool:
        """Check if article is duplicate"""
        content_hash = self.generate_hash(article)
        
        existing = db.query(ScrapedContent).filter(
            ScrapedContent.content_hash == content_hash
        ).first()
        
        return existing is not None