"""
Market Data Module
"""
from .api.routes_exchange import router as exchange_router
from .api.routes_market import router as market_router
from .api.routes_assets import router as assets_router
from .api.routes_whales import router as whales_router
from .api.routes_derivatives import router as derivatives_router
from .api.routes_redis import router as redis_router
from .api.routes_candles import router as candles_router

from .providers.registry import provider_registry
from .services.instrument_registry import instrument_registry
from .services.aggregator import aggregator
from .services.aggregation_engine import aggregation_engine
from .services.redis_pipeline import redis_pipeline
from .services.candle_ingestor import candle_ingestor

__all__ = [
    "exchange_router",
    "market_router", 
    "assets_router",
    "whales_router",
    "derivatives_router",
    "redis_router",
    "candles_router",
    "provider_registry",
    "instrument_registry",
    "aggregator",
    "aggregation_engine",
    "redis_pipeline",
    "candle_ingestor"
]
