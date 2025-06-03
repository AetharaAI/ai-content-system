#!/bin/bash
# AI Content Automation - Setup Script

set -e

echo "🚀 Setting up AI Content Automation System..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your API keys and configuration"
    echo "   Required: Add your OpenAI API key to OPENAI_API_KEY"
    echo "   Optional: Add other LLM API keys and publishing credentials"
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p data/postgres
mkdir -p logs

# Build and start services
echo "🐳 Building and starting services..."
docker-compose up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 30

# Check service health
echo "🏥 Checking service health..."
curl -f http://localhost:8001/health || echo "⚠️ Scraper service not ready"
curl -f http://localhost:8002/health || echo "⚠️ Summarizer service not ready"
curl -f http://localhost:8004/health || echo "⚠️ Dashboard service not ready"

echo ""
echo "✅ Setup completed!"
echo ""
echo "🎯 Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Restart services: docker-compose restart"
echo "3. Access dashboard: http://localhost:8004"
echo "4. Start scraping: curl -X POST http://localhost:8001/scrape"
echo ""
echo "📚 Service URLs:"
echo "   Dashboard: http://localhost:8004"
echo "   Scraper: http://localhost:8001"
echo "   Summarizer: http://localhost:8002"
echo ""
echo "🔧 Management commands:"
echo "   View logs: docker-compose logs -f"
echo "   Stop services: docker-compose down"
echo "   Restart services: docker-compose restart"