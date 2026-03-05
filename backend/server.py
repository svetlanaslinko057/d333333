"""
FOMO Market Data API
Unified Exchange Data Backend
"""

from fastapi import FastAPI
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI(
    title="FOMO Market Data API",
    version="2.0.0",
    description="Unified Exchange Data Backend - Binance, Bybit, Coinbase, Hyperliquid"
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# CORE ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "service": "FOMO Market Data API",
        "version": "2.0.0",
        "ts": int(time.time() * 1000),
        "layers": {
            "market_data": ["binance", "bybit", "coinbase", "hyperliquid"],
            "asset_intel": "coming_soon"
        }
    }

@app.get("/api")
async def root():
    return {
        "service": "FOMO Market Data API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "market": "/api/market/*",
            "assets": "/api/assets/*",
            "exchange": "/api/exchange/*",
            "whales": "/api/whales/*",
            "unlocks": "/api/unlocks/*"
        }
    }

# ═══════════════════════════════════════════════════════════════
# REGISTER MARKET DATA MODULE (Layer 1)
# ═══════════════════════════════════════════════════════════════

from modules.market_data import (
    exchange_router,
    market_router,
    assets_router,
    whales_router,
    derivatives_router,
    redis_router,
    candles_router
)

# Register routers
app.include_router(exchange_router)
app.include_router(market_router)
app.include_router(assets_router)
app.include_router(whales_router)
app.include_router(derivatives_router)
app.include_router(redis_router)
app.include_router(candles_router)

# ═══════════════════════════════════════════════════════════════
# REGISTER UNLOCKS MODULE (Layer 2)
# ═══════════════════════════════════════════════════════════════

from modules.unlocks import unlocks_router
app.include_router(unlocks_router)

# ═══════════════════════════════════════════════════════════════
# REGISTER INTEL MODULE (Layer 2 - Crypto Intelligence)
# ═══════════════════════════════════════════════════════════════

from modules.intel import intel_router, admin_router
app.include_router(intel_router)
app.include_router(admin_router)

# ═══════════════════════════════════════════════════════════════
# CORS & MIDDLEWARE
# ═══════════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# STARTUP / SHUTDOWN
# ═══════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    logger.info("FOMO Market Data API starting...")
    logger.info("Registered routes:")
    logger.info("  - /api/health")
    logger.info("  - /api/market/* (overview, assets)")
    logger.info("  - /api/assets/* (profile, performance, chart, venues)")
    logger.info("  - /api/exchange/* (instruments, ticker, orderbook, trades, candles)")
    logger.info("  - /api/derivatives/* (funding, open-interest, liquidations, long-short)")
    logger.info("  - /api/whales/* (snapshots, leaderboard)")
    logger.info("  - /api/candles/* (historical OHLCV from ClickHouse)")
    logger.info("  - /api/intel/* (crypto intelligence data)")
    
    # Sync instruments on startup
    from modules.market_data.services import instrument_registry
    try:
        await instrument_registry.sync_all(force=True)
        stats = instrument_registry.stats()
        logger.info(f"Instrument registry synced: {stats['total_instruments']} instruments, {stats['total_assets']} assets")
    except Exception as e:
        logger.warning(f"Failed to sync instruments on startup: {e}")
    
    # Start Redis Pipeline (Stage 5)
    from modules.market_data.services import redis_pipeline
    try:
        await redis_pipeline.start()
        logger.info("Redis Pipeline started")
    except Exception as e:
        logger.warning(f"Failed to start Redis Pipeline: {e}")
    
    # Start Candle Ingestor (Stage 7)
    from modules.market_data.services import candle_ingestor
    try:
        await candle_ingestor.start()
        logger.info("Candle Ingestor started")
    except Exception as e:
        logger.warning(f"Failed to start Candle Ingestor: {e}")
    
    # Start Intel Sync Scheduler (Layer 2)
    # Note: Scheduler is disabled by default to avoid unnecessary API calls
    # Enable via POST /api/intel/scheduler/start
    logger.info("Intel Scheduler available - start via POST /api/intel/scheduler/start")

@app.on_event("shutdown")
async def shutdown():
    # Stop Intel Scheduler
    from modules.intel.engine import stop_intel_scheduler
    try:
        await stop_intel_scheduler()
        logger.info("Intel Scheduler stopped")
    except Exception:
        pass
    
    # Stop Candle Ingestor
    from modules.market_data.services import candle_ingestor
    try:
        await candle_ingestor.stop()
    except Exception:
        pass
    
    # Stop Redis Pipeline
    from modules.market_data.services import redis_pipeline
    try:
        await redis_pipeline.stop()
    except Exception:
        pass
    
    client.close()
    logger.info("FOMO Market Data API shutdown")
