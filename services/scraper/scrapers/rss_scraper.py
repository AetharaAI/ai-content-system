import asyncio
import aiohttp
import feedparser
from typing import List, Dict, Optional
from datetime import datetime
import logging
from urllib.parse import urljoin, urlparse
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class RSScraper(BaseScraper):
    """RSS/Atom feed scraper"""
    
    async def scrape(self, feed_url: str, selectors: Dict = None) -> List[Dict]:
        """Scrape RSS/Atom feed"""
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={'User-Agent': self.user_agent}
            ) as session:
                async with session.get(feed_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch RSS feed {feed_url}: {response.status}")
                        return []
                    
                    content = await response.text()
                    
            # Parse RSS feed
            feed = feedparser.parse(content)
            
            if not feed.entries:
                logger.warning(f"No entries found in RSS feed: {feed_url}")
                return []
            
            articles = []
            
            for entry in feed.entries[:self.max_articles]:
                try:
                    article = await self._parse_rss_entry(entry, feed_url)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.error(f"Error parsing RSS entry: {e}")
                    continue
            
            logger.info(f"Successfully scraped {len(articles)} articles from {feed_url}")
            return articles
            
        except Exception as e:
            logger.error(f"Error scraping RSS feed {feed_url}: {e}")
            return []
    
    async def _parse_rss_entry(self, entry, feed_url: str) -> Optional[Dict]:
        """Parse individual RSS entry"""
        try:
            # Extract basic information
            title = entry.get('title', '').strip()
            link = entry.get('link', '').strip()
            
            if not title or not link:
                return None
            
            # Handle relative URLs
            parsed_feed = urlparse(feed_url)
            base_url = f"{parsed_feed.scheme}://{parsed_feed.netloc}"
            link = urljoin(base_url, link)
            
            # Extract content
            content = ""
            if hasattr(entry, 'content'):
                content = entry.content[0].value if entry.content else ""
            elif hasattr(entry, 'summary'):
                content = entry.summary
            elif hasattr(entry, 'description'):
                content = entry.description
            
            # Clean HTML from content
            content = self._clean_html(content)
            
            # Extract publish date
            published_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published_date = datetime(*entry.updated_parsed[:6])
            
            # Extract author
            author = ""
            if hasattr(entry, 'author'):
                author = entry.author
            elif hasattr(entry, 'authors') and entry.authors:
                author = entry.authors[0].get('name', '')
            
            # Extract tags/categories
            tags = []
            if hasattr(entry, 'tags'):
                tags = [tag.term for tag in entry.tags if hasattr(tag, 'term')]
            
            return {
                'title': title,
                'url': link,
                'content': content,
                'author': author,
                'published_date': published_date,
                'tags': tags,
                'source_type': 'rss'
            }
            
        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None