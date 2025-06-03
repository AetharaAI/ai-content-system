from .rss_scraper import RSScraper
from .html_scraper import HTMLScraper
from .base_scraper import BaseScraper

class JSScraper(BaseScraper):
    """Placeholder for JavaScript scraper"""
    async def scrape(self, url: str, selectors: dict = None):
        return []

__all__ = ['RSScraper', 'HTMLScraper', 'JSScraper', 'BaseScraper']