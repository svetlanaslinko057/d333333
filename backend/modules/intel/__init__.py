"""
Intel Module - Crypto Intelligence Layer

Data sources:
- Dropstab: SSR scraping (__NEXT_DATA__) - ~100 coins per page
- CryptoRank: JSON ingest from scraped data
- CoinGecko: market metrics, categories, trending (fallback)

Collections:
- intel_investors
- intel_unlocks  
- intel_fundraising
- intel_projects
- intel_activity
- intel_launchpads
- intel_categories
- intel_market
- moderation_queue
"""

from .api.routes import router as intel_router
from .api.routes_admin import router as admin_router
from .dropstab import DropstabSync, dropstab_scraper
from .sources.cryptorank import CryptoRankSync, cryptorank_client
from .sources.coingecko import CoinGeckoSync, coingecko_pool

__all__ = [
    'intel_router',
    'admin_router',
    'DropstabSync', 
    'dropstab_scraper',
    'CryptoRankSync',
    'cryptorank_client',
    'CoinGeckoSync',
    'coingecko_pool'
]
