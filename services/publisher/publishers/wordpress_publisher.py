# Add this to services/publisher/publishers/wordpress_publisher.py

import aiohttp
import base64
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class WordPressPublisher:
    def __init__(self, api_url: str, username: str, password: str):
        self.api_url = api_url.rstrip('/')
        self.username = username
        self.password = password
        self.auth_header = self._create_auth_header()
    
    def _create_auth_header(self) -> str:
        """Create basic auth header for WordPress"""
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    async def publish_article(self, content_data: Dict) -> Optional[Dict]:
        """Publish article to WordPress"""
        try:
            # Prepare WordPress post data
            post_data = {
                'title': content_data['title'],
                'content': self._format_content(content_data),
                'excerpt': content_data['description'],
                'status': 'publish',  # or 'draft' if you want to review first
                'categories': await self._get_or_create_category(content_data.get('category', 'AI News')),
                'tags': self._format_tags(content_data.get('hashtags', [])),
                'meta': {
                    '_yoast_wpseo_title': content_data['title'],
                    '_yoast_wpseo_metadesc': content_data['description']
                }
            }
            
            headers = {
                'Authorization': self.auth_header,
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/posts",
                    json=post_data,
                    headers=headers
                ) as response:
                    if response.status == 201:
                        result = await response.json()
                        logger.info(f"Successfully published to WordPress: {result['id']}")
                        return {
                            'success': True,
                            'id': result['id'],
                            'url': result['link'],
                            'status': result['status']
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"WordPress publish failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error publishing to WordPress: {e}")
            return None
    
    def _format_content(self, content_data: Dict) -> str:
        """Format content for WordPress"""
        html_content = f"""
        <div class="ai-generated-content">
            <p class="ai-summary">{content_data['summary']}</p>
            
            <div class="source-info" style="background: #f9f9f9; padding: 15px; border-left: 4px solid #0073aa; margin: 20px 0;">
                <p><strong>📰 Source:</strong> <a href="{content_data['original_url']}" target="_blank" rel="noopener">{content_data['source']}</a></p>
                <p><strong>🤖 AI Summary:</strong> This content was automatically generated from the latest AI and technology news.</p>
            </div>
            
            <div class="article-hashtags" style="margin-top: 20px;">
                {self._format_hashtags_html(content_data.get('hashtags', []))}
            </div>
            
            <div class="read-original" style="text-align: center; margin: 30px 0; padding: 20px; background: #e3f2fd; border-radius: 8px;">
                <p><strong>📖 Want to read the full original article?</strong></p>
                <a href="{content_data['original_url']}" target="_blank" rel="noopener" 
                   style="display: inline-block; background: #0073aa; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                   Read Full Article →
                </a>
            </div>
        </div>
        """
        return html_content
    
    def _format_hashtags_html(self, hashtags) -> str:
        """Format hashtags as HTML"""
        if not hashtags:
            return ""
        
        html = '<div class="hashtags" style="display: flex; flex-wrap: wrap; gap: 8px;">'
        for tag in hashtags:
            html += f'<span style="background: #e3f2fd; color: #1976d2; padding: 4px 12px; border-radius: 15px; font-size: 14px;">{tag}</span>'
        html += '</div>'
        return html
    
    def _format_tags(self, hashtags) -> list:
        """Convert hashtags to WordPress tags"""
        return [tag.replace('#', '').strip() for tag in hashtags if tag.strip()]
    
    async def _get_or_create_category(self, category_name: str) -> list:
        """Get or create WordPress category"""
        try:
            headers = {'Authorization': self.auth_header}
            
            async with aiohttp.ClientSession() as session:
                # First, try to find existing category
                async with session.get(
                    f"{self.api_url}/categories?search={category_name}",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        categories = await response.json()
                        if categories:
                            return [categories[0]['id']]
                
                # Create new category if not found
                category_data = {
                    'name': category_name,
                    'description': f'Articles about {category_name}'
                }
                
                async with session.post(
                    f"{self.api_url}/categories",
                    json=category_data,
                    headers=headers
                ) as response:
                    if response.status == 201:
                        new_category = await response.json()
                        return [new_category['id']]
                    
        except Exception as e:
            logger.error(f"Error with WordPress categories: {e}")
        
        # Fallback to default category
        return [1]  # WordPress default "Uncategorized" category