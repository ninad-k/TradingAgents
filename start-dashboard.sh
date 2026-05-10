#!/bin/bash

set -e

echo "🚀 Trading Dashboard Quick Start"
echo "================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo "${YELLOW}⚠️  .env file not found. Creating from .env.example...${NC}"
    cp .env.example .env
    echo "${GREEN}✓ .env created${NC}"
fi

# Check TRADING_MODE
if grep -q "TRADING_MODE=paper" .env; then
    echo "${GREEN}✓ Paper trading mode confirmed in .env${NC}"
else
    echo "${YELLOW}⚠️  Adding TRADING_MODE=paper to .env${NC}"
    echo "" >> .env
    echo "# Added by start-dashboard.sh" >> .env
    echo "TRADING_MODE=paper" >> .env
fi

echo ""
echo "${BLUE}Installation & Setup${NC}"
echo "-------------------"

# Install dashboard dependencies
echo "${YELLOW}Installing FastAPI dependencies...${NC}"
pip install -q fastapi uvicorn pydantic 2>/dev/null || pip install fastapi uvicorn pydantic

echo "${GREEN}✓ FastAPI dependencies installed${NC}"

# Install frontend dependencies
if [ -d "tradingagents/frontend" ]; then
    echo ""
    echo "${YELLOW}Installing React frontend dependencies...${NC}"
    cd tradingagents/frontend
    npm install --quiet 2>/dev/null || npm install
    echo "${GREEN}✓ Frontend dependencies installed${NC}"
    cd ../..
fi

echo ""
echo "${BLUE}Starting Services${NC}"
echo "----------------"
echo ""
echo "${YELLOW}Available options:${NC}"
echo ""
echo "Option 1: Run terminal dashboard only (Phase 1 & 2)"
echo "  python -m cli.main analyze"
echo ""
echo "Option 2: Start backend API (Phase 3)"
echo "  python -m uvicorn tradingagents.api.dashboard_api:app --host 127.0.0.1 --port 8000 --reload"
echo ""
echo "Option 3: Start React frontend (Phase 3)"
echo "  cd tradingagents/frontend && npm run dev"
echo ""
echo "Option 4: Run all services (requires 3 terminals)"
echo "  # Terminal 1:"
echo "  python -m cli.main analyze"
echo "  # Terminal 2:"
echo "  python -m uvicorn tradingagents.api.dashboard_api:app --host 127.0.0.1 --port 8000 --reload"
echo "  # Terminal 3:"
echo "  cd tradingagents/frontend && npm run dev"
echo "  # Then open: http://localhost:3000"
echo ""
echo "${GREEN}Setup complete! Choose an option above to get started.${NC}"
echo ""
echo "📖 For detailed setup instructions, see DASHBOARD_SETUP.md"
echo "📋 For implementation details, see TRADING_DASHBOARD_SUMMARY.md"
