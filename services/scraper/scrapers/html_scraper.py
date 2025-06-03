import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class HTMLScraper(BaseScraper):
    """HTML page scraper using CSS selectors"""
    
    async def scrape(self, url: str, selectors: Dict) -> List[Dict]:
        """Scrape HTML page using provided selectors"""
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={'User-Agent': self.user_agent}
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch HTML page {url}: {response.status}")
                        return []
                    
                    html_content = await response.text()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            articles = []
            
            # Find article containers
            article_containers = soup.select(selectors.get('container', 'article, .post, .story'))
            
            for container in article_containers[:self.max_articles]:
                try:
                    article = await self._parse_html_article(container, selectors, url)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.error(f"Error parsing HTML article: {e}")
                    continue
            
            logger.info(f"Successfully scraped {len(articles)} articles from {url}")
            return articles
            
        except Exception as e:
            logger.error(f"Error scraping HTML page {url}: {e}")
            return []
    
    async def _parse_html_article(self, container, selectors: Dict, base_url: str) -> Optional[Dict]:
        """Parse individual HTML article"""
        try:
            # Extract title
            title_elem = container.select_one(selectors.get('title', 'h1, h2, h3, .title'))
            title = self._extract_text_content(title_elem) if title_elem else ""
            
            # Extract link
            link_elem = container.select_one(selectors.get('link', 'a'))
            link = ""
            if link_elem:
                link = link_elem.get('href', '')
                if link and not link.startswith('http'):
                    from urllib.parse import urljoin
                    link = urljoin(base_url, link)
            
            # Extract content
            content_elem = container.select_one(selectors.get('content', '.content, .body, p'))
            content = self._extract_text_content(content_elem) if content_elem else ""
            
            # Extract author
            author_elem = container.select_one(selectors.get('author', '.author, .byline'))
            author = self._extract_text_content(author_elem) if author_elem else ""
            
            if not title or not link:
                return None
            
            return {
                'title': title,
                'url': link,
                'content': content,
                'author': author,
                'published_date': datetime.utcnow(),  # Default to now
                'source_type': 'html'
            }
            
        except Exception as e:
            logger.error(f"Error parsing HTML article: {e}")
            return None