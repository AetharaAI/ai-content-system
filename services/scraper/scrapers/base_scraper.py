from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import re
from bs4 import BeautifulSoup
import html

class BaseScraper(ABC):
    def __init__(self):
        self.max_articles = 50
        self.user_agent = "Mozilla/5.0 (compatible; AIContentBot/1.0)"
    
    @abstractmethod
    async def scrape(self, url: str, selectors: Dict = None) -> List[Dict]:
        """Scrape content from URL"""
        pass
    
    def _clean_html(self, text: str) -> str:
        """Clean HTML tags and decode entities"""
        if not text:
            return ""
        
        # Remove HTML tags
        soup = BeautifulSoup(text, 'html.parser')
        cleaned = soup.get_text()
        
        # Decode HTML entities
        cleaned = html.unescape(cleaned)
        
        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _extract_text_content(self, element) -> str:
        """Extract clean text from BeautifulSoup element"""
        if not element:
            return ""
        
        # Remove script and style elements
        for script in element(["script", "style"]):
            script.decompose()
        
        return self._clean_html(str(element))