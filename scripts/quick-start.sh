#!/bin/bash
# Quick start script for immediate testing

set -e

echo "🚀 Quick Start - AI Content Automation"

# Start only essential services for testing
echo "🐳 Starting essential services..."
docker-compose up -d postgres redis scraper

# Wait for database
echo "⏳ Waiting for database..."
sleep 15

# Trigger initial scraping
echo "📰 Starting initial content scraping..."
curl -X POST http://localhost:8001/scrape

echo ""
echo "✅ Quick start completed!"
echo ""
echo "📊 Check scraping status:"
echo "   curl http://localhost:8001/scrape/status"
echo ""
echo "🔍 View scraped content:"
echo "   curl http://localhost:8001/health"
echo ""
echo "📈 Next steps:"
echo "1. Add OpenAI API key to .env file"
echo "2. Start summarizer: docker-compose up -d summarizer"
echo "3. Process content: curl -X POST http://localhost:8002/process"