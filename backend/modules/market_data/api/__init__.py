"""API routes"""
from .routes_exchange import router as exchange_router
from .routes_market import router as market_router
from .routes_assets import router as assets_router
from .routes_whales import router as whales_router
from .routes_derivatives import router as derivatives_router
from .routes_redis import router as redis_router
