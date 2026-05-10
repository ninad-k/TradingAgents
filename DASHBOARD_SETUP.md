# Trading Dashboard Setup Guide

This guide walks you through setting up and running the three-phase trading dashboard system: paper trading configuration, enhanced terminal dashboard, and web-based React dashboard.

## Overview

### Phase 1: Paper Trading Configuration ✅
- **What it does:** Explicitly sets trading mode (paper vs. live)
- **Configuration:** `TRADING_MODE` environment variable in `.env`
- **Default:** `paper` (safe demo mode)
- **Files modified:**
  - `tradingagents/default_config.py` - Added `trading_mode` config
  - `.env.example` - Added `TRADING_MODE=paper` with warning
  - `tradingagents/brokers/mt5_connector.py` - Reads config and logs trading mode
  - `cli/main.py` - Displays trading mode at startup

### Phase 2: Enhanced Terminal Dashboard ✅
- **What it does:** Rich-formatted real-time dashboard in terminal
- **Features:** Tables, metrics, recent activity with timestamps
- **Files modified:**
  - `tradingagents/brokers/analytics.py` - Added Rich library support

### Phase 3: Web Dashboard ✅
- **What it does:** Professional React UI for monitoring trades
- **Architecture:** FastAPI backend + React Vite frontend
- **Files created:**
  - `tradingagents/api/` - FastAPI backend with endpoints and WebSocket
  - `tradingagents/frontend/` - React Vite project with TypeScript

---

## Getting Started

### Step 1: Configure Paper Trading (Phase 1)

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Verify `TRADING_MODE=paper` is set:

```env
TRADING_MODE=paper
```

⚠️ **WARNING:** Never set to `TRADING_MODE=live` without full understanding of implications. This trades real money.

### Step 2: Run the App with Terminal Dashboard (Phases 1 & 2)

```bash
# Make sure environment is set up
source .venv/bin/activate  # or activate your venv

# Run the trading analysis
python -m cli.main analyze
```

You'll see:
- ✅ **"Running in PAPER TRADING MODE"** banner at startup
- 📊 Enhanced terminal dashboard with Rich-formatted tables
- Real-time metrics for decisions, executions, rejections

### Step 3: Run the Web Dashboard (Phase 3)

#### 3a. Start the FastAPI Backend

```bash
# In terminal window 1
pip install fastapi uvicorn pydantic

cd /Users/ninadk/PycharmProjects/TradingAgents

python -m uvicorn tradingagents.api.dashboard_api:app --host 127.0.0.1 --port 8000 --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

#### 3b. Install React Dependencies

```bash
# In terminal window 2
cd /Users/ninadk/PycharmProjects/TradingAgents/tradingagents/frontend

npm install
```

#### 3c. Start the React Dev Server

```bash
# Still in frontend directory
npm run dev
```

You should see:
```
VITE v5.0.2  ready in 123 ms

➜  Local:   http://localhost:3000/
```

#### 3d. Open the Dashboard

Open your browser to: **http://localhost:3000**

You should see a professional dashboard with:
- ✅ Trading mode badge (Paper/Live)
- 💰 Account balance and metrics
- 📈 Performance charts
- 💱 Open positions
- 📜 Trade history

---

## Testing the Dashboard

### Test 1: Verify Paper Trading is Active

Look for the **green "PAPER" badge** in the top-right corner of:
1. Terminal output: "Running in PAPER TRADING MODE"
2. Web dashboard: Green "PAPER" badge

### Test 2: Verify Real-Time Updates

1. Keep the FastAPI backend running
2. Keep the React dashboard open
3. Run an analysis: `python -m cli.main analyze`
4. Watch the dashboard update in real-time as trades execute

### Test 3: Check API Endpoints

Test the API directly:

```bash
# Get account status
curl http://localhost:8000/api/status

# Get recent trades
curl http://localhost:8000/api/trades

# Get portfolio summary
curl http://localhost:8000/api/portfolio

# Get analytics
curl http://localhost:8000/api/analytics
```

---

## Architecture

### Backend (FastAPI)
```
tradingagents/api/
├── __init__.py
├── models.py           # Pydantic models for type safety
└── dashboard_api.py    # FastAPI app with endpoints & WebSocket
```

**Endpoints:**
- `GET /health` - Health check
- `GET /api/status` - Current dashboard status
- `GET /api/trades` - Recent trades (limit param)
- `GET /api/portfolio` - Portfolio summary
- `GET /api/analytics` - Detailed analytics
- `WebSocket /ws/live-updates` - Real-time status updates

### Frontend (React + Vite)
```
tradingagents/frontend/
├── src/
│   ├── App.tsx                      # Main app component
│   ├── api.ts                       # API client
│   ├── types.ts                     # TypeScript types
│   ├── App.css                      # Styling (dark theme)
│   ├── components/
│   │   ├── Dashboard.tsx            # Main dashboard layout
│   │   ├── MetricsCards.tsx         # Key metrics cards
│   │   ├── AccountOverview.tsx      # Account details
│   │   ├── PortfolioSummary.tsx     # Open positions
│   │   ├── TradeHistory.tsx         # Trade log table
│   │   └── PerformanceChart.tsx     # Charts (Recharts)
│   └── main.tsx                     # React entry point
├── package.json
├── vite.config.ts
├── tsconfig.json
└── index.html
```

---

## Configuration

### Environment Variables

**`.env` file:**
```env
# Trading Mode: "paper" (safe demo) or "live" (real money)
TRADING_MODE=paper

# LLM Provider (keep your existing config)
OPENAI_API_KEY=your_key_here
```

### API Configuration

The API automatically:
- Binds to `127.0.0.1:8000` (localhost only, secure)
- Disables CORS (no external access)
- Provides WebSocket updates every 2 seconds
- Reads trading mode from config

### Frontend Configuration

The React app automatically:
- Connects to `http://localhost:8000` (hardcoded for localhost)
- Establishes WebSocket connection for live updates
- Falls back gracefully if API is unavailable

---

## Troubleshooting

### Issue: Dashboard shows "Connecting..."
**Solution:** Ensure FastAPI backend is running on port 8000:
```bash
curl http://localhost:8000/health
```

### Issue: WebSocket connection fails
**Solution:** Check that both backend and frontend are running:
1. Backend: `http://localhost:8000` (in a terminal)
2. Frontend: `http://localhost:3000` (in browser)

### Issue: "Failed to connect to trading dashboard API"
**Solution:** 
1. Start the FastAPI backend first
2. Wait a few seconds for it to initialize
3. Refresh the browser

### Issue: API returns empty data
**Solution:** Run an analysis to generate trading data:
```bash
python -m cli.main analyze
```

---

## Production Deployment

For production use:

1. **Backend:**
   ```bash
   python -m uvicorn tradingagents.api.dashboard_api:app --host 0.0.0.0 --port 8000
   ```
   - Add authentication middleware
   - Enable CORS only for your domain
   - Use HTTPS in production

2. **Frontend:**
   ```bash
   cd tradingagents/frontend
   npm run build
   ```
   - Serves static files from `dist/` directory
   - Update API endpoint configuration for production

---

## Next Steps

1. ✅ Configure paper trading: Set `TRADING_MODE=paper` in `.env`
2. ✅ Run the app: `python -m cli.main analyze`
3. ✅ Monitor in terminal: Watch the enhanced dashboard
4. ✅ Start backend: `python -m uvicorn tradingagents.api.dashboard_api:app ...`
5. ✅ Start frontend: `cd tradingagents/frontend && npm run dev`
6. ✅ Open dashboard: Navigate to `http://localhost:3000`

---

## Support

For issues or questions:
- Check the troubleshooting section above
- Review the implementation in `tradingagents/api/` and `tradingagents/frontend/`
- Check logs in FastAPI terminal output
- Check browser console for frontend errors
