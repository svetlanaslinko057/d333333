"""
CoinGecko Sync Service
Fetches and stores market data from CoinGecko
Used as fallback when Dropstab/CryptoRank data is missing
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from .client import coingecko_client, coingecko_pool
from ...common.storage import upsert_with_diff

logger = logging.getLogger(__name__)


class CoinGeckoSync:
    """
    Sync service for CoinGecko data.
    Handles fetching and storing market metrics.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.client = coingecko_client
    
    async def sync_global_market(self) -> Dict[str, Any]:
        """Sync global market data"""
        logger.info("[CoinGecko] Syncing global market...")
        
        data = await self.client.get_global()
        if not data:
            return {'error': 'Failed to fetch global data'}
        
        doc = {
            'key': 'coingecko:global:latest',
            'source': 'coingecko',
            'total_market_cap_usd': data.get('total_market_cap', {}).get('usd', 0),
            'total_volume_24h_usd': data.get('total_volume', {}).get('usd', 0),
            'btc_dominance': data.get('market_cap_percentage', {}).get('btc', 0),
            'eth_dominance': data.get('market_cap_percentage', {}).get('eth', 0),
            'active_cryptocurrencies': data.get('active_cryptocurrencies', 0),
            'markets': data.get('markets', 0),
            'market_cap_change_24h': data.get('market_cap_change_percentage_24h_usd', 0),
            'updated_at': datetime.now(timezone.utc)
        }
        
        await self.db.intel_market.update_one(
            {'key': doc['key']},
            {'$set': doc},
            upsert=True
        )
        
        logger.info(f"[CoinGecko] Global market synced: MCap=${doc['total_market_cap_usd']:,.0f}")
        return {'synced': 1}
    
    async def sync_categories(self) -> Dict[str, Any]:
        """Sync category data"""
        logger.info("[CoinGecko] Syncing categories...")
        
        data = await self.client.get_categories()
        if not data:
            return {'error': 'Failed to fetch categories'}
        
        saved = 0
        for cat in data:
            doc = {
                'key': f"coingecko:category:{cat.get('id', '')}",
                'source': 'coingecko',
                'category_id': cat.get('id', ''),
                'name': cat.get('name', ''),
                'market_cap': cat.get('market_cap', 0),
                'market_cap_change_24h': cat.get('market_cap_change_24h', 0),
                'volume_24h': cat.get('volume_24h', 0),
                'top_3_coins': cat.get('top_3_coins', []),
                'updated_at': datetime.now(timezone.utc)
            }
            
            result = await upsert_with_diff(self.db.intel_categories, doc)
            if result['changed']:
                saved += 1
        
        logger.info(f"[CoinGecko] Categories: {len(data)} total, {saved} changed")
        return {'total': len(data), 'changed': saved}
    
    async def sync_trending(self) -> Dict[str, Any]:
        """Sync trending coins"""
        logger.info("[CoinGecko] Syncing trending...")
        
        data = await self.client.get_trending()
        if not data:
            return {'error': 'Failed to fetch trending'}
        
        coins = data.get('coins', [])
        saved = 0
        
        for item in coins:
            coin = item.get('item', {})
            doc = {
                'key': f"coingecko:trending:{coin.get('id', '')}",
                'source': 'coingecko',
                'type': 'trending',
                'coin_id': coin.get('id', ''),
                'symbol': coin.get('symbol', '').upper(),
                'name': coin.get('name', ''),
                'market_cap_rank': coin.get('market_cap_rank'),
                'score': coin.get('score', 0),
                'thumb': coin.get('thumb', ''),
                'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'updated_at': datetime.now(timezone.utc)
            }
            
            await self.db.intel_activity.update_one(
                {'key': doc['key']},
                {'$set': doc},
                upsert=True
            )
            saved += 1
        
        logger.info(f"[CoinGecko] Trending: {saved} coins")
        return {'total': saved}
    
    async def sync_top_coins(self, limit: int = 100) -> Dict[str, Any]:
        """Sync top coins by market cap"""
        logger.info(f"[CoinGecko] Syncing top {limit} coins...")
        
        data = await self.client.get_markets(per_page=min(limit, 250))
        if not data:
            return {'error': 'Failed to fetch markets'}
        
        saved = 0
        for coin in data:
            doc = self._parse_coin_market(coin)
            result = await upsert_with_diff(self.db.intel_projects, doc)
            if result['changed']:
                saved += 1
        
        logger.info(f"[CoinGecko] Top coins: {len(data)} total, {saved} changed")
        return {'total': len(data), 'changed': saved}
    
    async def sync_markets_full(self, max_pages: int = 60) -> Dict[str, Any]:
        """
        Full market sync with pagination.
        CoinGecko /coins/markets allows 250 coins per page.
        60 pages = ~15000 coins (full market coverage)
        
        Throttling: 1.2 sec delay = ~50 req/min (safe for free tier)
        Total time: ~72 seconds for full sync
        """
        import asyncio
        
        logger.info(f"[CoinGecko] Starting FULL market sync (up to {max_pages} pages, ~{max_pages * 250} coins)...")
        start_time = asyncio.get_event_loop().time()
        
        total = 0
        changed = 0
        empty_pages = 0
        errors = 0
        
        for page in range(1, max_pages + 1):
            try:
                data = await self.client.get_markets(per_page=250, page=page)
                
                if not data or len(data) == 0:
                    empty_pages += 1
                    if empty_pages >= 3:
                        logger.info(f"[CoinGecko] No more data at page {page}, stopping")
                        break
                    continue
                
                empty_pages = 0  # Reset counter on success
                
                for coin in data:
                    doc = self._parse_coin_market(coin)
                    result = await upsert_with_diff(self.db.intel_projects, doc)
                    total += 1
                    if result['changed']:
                        changed += 1
                
                # Log progress every 10 pages
                if page % 10 == 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    logger.info(f"[CoinGecko] Progress: page {page}/{max_pages}, {total} coins, {elapsed:.1f}s elapsed")
                
                # Throttling: 1.2 sec between requests (safe rate limit)
                await asyncio.sleep(1.2)
                
            except Exception as e:
                errors += 1
                logger.error(f"[CoinGecko] Page {page} error: {e}")
                # On rate limit, wait longer
                if '429' in str(e):
                    logger.warning("[CoinGecko] Rate limited, waiting 60s...")
                    await asyncio.sleep(60)
                continue
        
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info(f"[CoinGecko] Full market sync complete: {total} coins, {changed} changed, {elapsed:.1f}s")
        return {
            'source': 'coingecko',
            'entity': 'markets_full',
            'total': total,
            'changed': changed,
            'pages': page,
            'errors': errors,
            'elapsed_sec': round(elapsed, 1)
        }
    
    async def sync_coin(self, coin_id: str) -> Dict[str, Any]:
        """Sync single coin with full details"""
        logger.info(f"[CoinGecko] Syncing coin: {coin_id}")
        
        data = await self.client.get_coin(coin_id)
        if not data:
            return {'error': f'Coin not found: {coin_id}'}
        
        doc = self._parse_coin_detail(data)
        result = await upsert_with_diff(self.db.intel_projects, doc)
        
        logger.info(f"[CoinGecko] Coin {coin_id}: {'changed' if result['changed'] else 'unchanged'}")
        return {'coin_id': coin_id, 'changed': result['changed']}
    
    async def sync_coins_batch(self, coin_ids: List[str]) -> Dict[str, Any]:
        """Sync multiple coins efficiently"""
        logger.info(f"[CoinGecko] Batch syncing {len(coin_ids)} coins...")
        
        # Split into chunks of 250
        chunks = [coin_ids[i:i+250] for i in range(0, len(coin_ids), 250)]
        total = 0
        changed = 0
        
        for chunk in chunks:
            data = await self.client.get_coin_market_data(chunk)
            for coin in data:
                doc = self._parse_coin_market(coin)
                result = await upsert_with_diff(self.db.intel_projects, doc)
                total += 1
                if result['changed']:
                    changed += 1
        
        logger.info(f"[CoinGecko] Batch sync: {total} total, {changed} changed")
        return {'total': total, 'changed': changed}
    
    async def sync_all(self) -> Dict[str, Any]:
        """Run full sync"""
        logger.info("[CoinGecko] Starting full sync...")
        
        results = {
            'source': 'coingecko',
            'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
            'syncs': {}
        }
        
        try:
            results['syncs']['global'] = await self.sync_global_market()
        except Exception as e:
            logger.error(f"[CoinGecko] Global sync failed: {e}")
            results['syncs']['global'] = {'error': str(e)}
        
        try:
            results['syncs']['categories'] = await self.sync_categories()
        except Exception as e:
            logger.error(f"[CoinGecko] Categories sync failed: {e}")
            results['syncs']['categories'] = {'error': str(e)}
        
        try:
            results['syncs']['trending'] = await self.sync_trending()
        except Exception as e:
            logger.error(f"[CoinGecko] Trending sync failed: {e}")
            results['syncs']['trending'] = {'error': str(e)}
        
        try:
            results['syncs']['top_coins'] = await self.sync_top_coins(100)
        except Exception as e:
            logger.error(f"[CoinGecko] Top coins sync failed: {e}")
            results['syncs']['top_coins'] = {'error': str(e)}
        
        return results
    
    def _parse_coin_market(self, coin: Dict) -> Dict:
        """Parse coin market data into standard format"""
        return {
            'key': f"coingecko:{coin.get('id', '')}",
            'source': 'coingecko',
            'coin_id': coin.get('id', ''),
            'symbol': coin.get('symbol', '').upper(),
            'name': coin.get('name', ''),
            'image': coin.get('image', ''),
            'market_cap_rank': coin.get('market_cap_rank'),
            # Market metrics
            'price_usd': coin.get('current_price', 0),
            'market_cap': coin.get('market_cap', 0),
            'fully_diluted_valuation': coin.get('fully_diluted_valuation'),
            'total_volume': coin.get('total_volume', 0),
            # Supply
            'circulating_supply': coin.get('circulating_supply'),
            'total_supply': coin.get('total_supply'),
            'max_supply': coin.get('max_supply'),
            # Changes
            'price_change_24h': coin.get('price_change_24h', 0),
            'price_change_percentage_24h': coin.get('price_change_percentage_24h', 0),
            'price_change_percentage_7d': coin.get('price_change_percentage_7d_in_currency', 0),
            'price_change_percentage_30d': coin.get('price_change_percentage_30d_in_currency', 0),
            'market_cap_change_24h': coin.get('market_cap_change_24h', 0),
            'market_cap_change_percentage_24h': coin.get('market_cap_change_percentage_24h', 0),
            # ATH/ATL
            'ath': coin.get('ath', 0),
            'ath_change_percentage': coin.get('ath_change_percentage', 0),
            'ath_date': coin.get('ath_date'),
            'atl': coin.get('atl', 0),
            'atl_change_percentage': coin.get('atl_change_percentage', 0),
            'atl_date': coin.get('atl_date'),
            # Meta
            'last_updated': coin.get('last_updated'),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def _parse_coin_detail(self, coin: Dict) -> Dict:
        """Parse full coin detail"""
        market_data = coin.get('market_data', {})
        
        doc = {
            'key': f"coingecko:{coin.get('id', '')}",
            'source': 'coingecko',
            'coin_id': coin.get('id', ''),
            'symbol': coin.get('symbol', '').upper(),
            'name': coin.get('name', ''),
            'description': coin.get('description', {}).get('en', '')[:500],
            'categories': coin.get('categories', []),
            'image': coin.get('image', {}).get('large', ''),
            'market_cap_rank': coin.get('market_cap_rank'),
            # Links
            'homepage': coin.get('links', {}).get('homepage', [None])[0],
            'twitter': coin.get('links', {}).get('twitter_screen_name'),
            'telegram': coin.get('links', {}).get('telegram_channel_identifier'),
            'github': coin.get('links', {}).get('repos_url', {}).get('github', [None])[0],
            # Market data
            'price_usd': market_data.get('current_price', {}).get('usd', 0),
            'market_cap': market_data.get('market_cap', {}).get('usd', 0),
            'fully_diluted_valuation': market_data.get('fully_diluted_valuation', {}).get('usd'),
            'total_volume': market_data.get('total_volume', {}).get('usd', 0),
            # Supply
            'circulating_supply': market_data.get('circulating_supply'),
            'total_supply': market_data.get('total_supply'),
            'max_supply': market_data.get('max_supply'),
            # Changes
            'price_change_percentage_24h': market_data.get('price_change_percentage_24h', 0),
            'price_change_percentage_7d': market_data.get('price_change_percentage_7d', 0),
            'price_change_percentage_30d': market_data.get('price_change_percentage_30d', 0),
            # ATH/ATL
            'ath': market_data.get('ath', {}).get('usd', 0),
            'ath_date': market_data.get('ath_date', {}).get('usd'),
            'atl': market_data.get('atl', {}).get('usd', 0),
            'atl_date': market_data.get('atl_date', {}).get('usd'),
            # Genesis
            'genesis_date': coin.get('genesis_date'),
            # Meta
            'updated_at': datetime.now(timezone.utc)
        }
        
        return doc
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get API pool status"""
        return coingecko_pool.get_status()
