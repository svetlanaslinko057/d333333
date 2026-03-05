"""
Data Aggregator
Merges data from multiple sources based on priority and field configuration

Logic:
1. Each field can have its own source priority
2. Higher priority source data takes precedence
3. Fallback to lower priority sources for missing fields
4. Track data provenance (which source provided which field)
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class DataAggregator:
    """
    Aggregates data from multiple sources based on priority.
    
    Example field config:
    {
        "market_cap": {"source_priority": ["dropstab", "coingecko", "cryptorank"]},
        "fdv": {"source_priority": ["coingecko", "dropstab"]},
        "investors": {"source_priority": ["cryptorank", "dropstab"]}
    }
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._field_config_cache: Dict[str, Dict] = {}
    
    async def get_field_config(self, entity: str) -> Dict[str, Any]:
        """Get field configuration for entity type"""
        if entity in self._field_config_cache:
            return self._field_config_cache[entity]
        
        config = await self.db.field_config.find_one({'entity': entity}, {'_id': 0})
        if config:
            self._field_config_cache[entity] = config.get('fields', {})
        else:
            self._field_config_cache[entity] = {}
        
        return self._field_config_cache[entity]
    
    def invalidate_cache(self, entity: Optional[str] = None):
        """Invalidate field config cache"""
        if entity:
            self._field_config_cache.pop(entity, None)
        else:
            self._field_config_cache.clear()
    
    async def get_project(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get aggregated project data from all sources.
        Merges fields based on priority configuration.
        """
        symbol = symbol.upper()
        
        # Fetch from all sources
        sources_data = {}
        
        # Dropstab
        dropstab_doc = await self.db.intel_projects.find_one(
            {'symbol': symbol, 'source': 'dropstab'}, 
            {'_id': 0}
        )
        if dropstab_doc:
            sources_data['dropstab'] = dropstab_doc
        
        # CryptoRank
        cryptorank_doc = await self.db.intel_projects.find_one(
            {'symbol': symbol, 'source': 'cryptorank'}, 
            {'_id': 0}
        )
        if cryptorank_doc:
            sources_data['cryptorank'] = cryptorank_doc
        
        # CoinGecko (search by symbol is less reliable, try name match)
        coingecko_doc = await self.db.intel_projects.find_one(
            {'symbol': symbol, 'source': 'coingecko'}, 
            {'_id': 0}
        )
        if coingecko_doc:
            sources_data['coingecko'] = coingecko_doc
        
        if not sources_data:
            return None
        
        # Merge based on priority
        return await self._merge_project_data(symbol, sources_data)
    
    async def _merge_project_data(
        self, 
        symbol: str, 
        sources_data: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Merge project data from multiple sources"""
        
        field_config = await self.get_field_config('project')
        
        # Default source priority
        default_priority = ['dropstab', 'cryptorank', 'coingecko']
        
        # Result document
        merged = {
            'symbol': symbol,
            'sources': list(sources_data.keys()),
            '_provenance': {},  # Track which source provided which field
            'merged_at': datetime.now(timezone.utc)
        }
        
        # Fields to merge
        merge_fields = [
            # Identity
            'name', 'coin_id', 'image', 'description', 'categories',
            # Market metrics
            'price_usd', 'market_cap', 'fully_diluted_valuation', 'total_volume',
            'market_cap_rank',
            # Supply
            'circulating_supply', 'total_supply', 'max_supply',
            # Changes
            'price_change_percentage_24h', 'price_change_percentage_7d', 
            'price_change_percentage_30d', 'market_cap_change_24h',
            # ATH/ATL
            'ath', 'ath_date', 'atl', 'atl_date',
            # Project info
            'homepage', 'twitter', 'telegram', 'github', 'genesis_date',
            # Funding
            'total_raised', 'ico_price', 'listing_date'
        ]
        
        for field in merge_fields:
            # Get priority for this field
            priority = field_config.get(field, {}).get('source_priority', default_priority)
            
            # Find first source with non-null value
            for source in priority:
                if source in sources_data:
                    value = sources_data[source].get(field)
                    if value is not None:
                        merged[field] = value
                        merged['_provenance'][field] = source
                        break
        
        return merged
    
    async def get_investor(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get aggregated investor data"""
        
        sources_data = {}
        
        # Dropstab
        dropstab_doc = await self.db.intel_investors.find_one(
            {'slug': slug, 'source': 'dropstab'}, 
            {'_id': 0}
        )
        if dropstab_doc:
            sources_data['dropstab'] = dropstab_doc
        
        # CryptoRank
        cryptorank_doc = await self.db.intel_investors.find_one(
            {'slug': slug, 'source': 'cryptorank'}, 
            {'_id': 0}
        )
        if cryptorank_doc:
            sources_data['cryptorank'] = cryptorank_doc
        
        if not sources_data:
            return None
        
        return await self._merge_investor_data(slug, sources_data)
    
    async def _merge_investor_data(
        self, 
        slug: str, 
        sources_data: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Merge investor data"""
        
        field_config = await self.get_field_config('investor')
        default_priority = ['cryptorank', 'dropstab']
        
        merged = {
            'slug': slug,
            'sources': list(sources_data.keys()),
            '_provenance': {},
            'merged_at': datetime.now(timezone.utc)
        }
        
        merge_fields = [
            'name', 'tier', 'type', 'image', 'description',
            'investments_count', 'portfolio', 'total_invested',
            'website', 'twitter', 'last_investment_date'
        ]
        
        for field in merge_fields:
            priority = field_config.get(field, {}).get('source_priority', default_priority)
            
            for source in priority:
                if source in sources_data:
                    value = sources_data[source].get(field)
                    if value is not None:
                        merged[field] = value
                        merged['_provenance'][field] = source
                        break
        
        return merged
    
    async def get_unlock(self, key: str) -> Optional[Dict[str, Any]]:
        """Get unlock data, prefer Dropstab for schedule, CryptoRank for USD values"""
        
        sources_data = {}
        
        dropstab_doc = await self.db.intel_unlocks.find_one(
            {'key': {'$regex': f'^dropstab:.*:{key}$'}}, 
            {'_id': 0}
        )
        if dropstab_doc:
            sources_data['dropstab'] = dropstab_doc
        
        cryptorank_doc = await self.db.intel_unlocks.find_one(
            {'key': {'$regex': f'^cryptorank:.*:{key}$'}}, 
            {'_id': 0}
        )
        if cryptorank_doc:
            sources_data['cryptorank'] = cryptorank_doc
        
        if not sources_data:
            return None
        
        # For unlocks, merge with CryptoRank priority for USD values
        merged = {
            'key': key,
            'sources': list(sources_data.keys()),
            '_provenance': {},
            'merged_at': datetime.now(timezone.utc)
        }
        
        # Schedule fields prefer Dropstab
        schedule_fields = ['unlock_date', 'unlock_percent', 'vesting_schedule']
        for field in schedule_fields:
            for source in ['dropstab', 'cryptorank']:
                if source in sources_data:
                    value = sources_data[source].get(field)
                    if value is not None:
                        merged[field] = value
                        merged['_provenance'][field] = source
                        break
        
        # USD values prefer CryptoRank
        usd_fields = ['unlock_usd', 'tokens_amount', 'circulating_impact']
        for field in usd_fields:
            for source in ['cryptorank', 'dropstab']:
                if source in sources_data:
                    value = sources_data[source].get(field)
                    if value is not None:
                        merged[field] = value
                        merged['_provenance'][field] = source
                        break
        
        # Copy remaining fields from first available source
        for source_data in sources_data.values():
            for k, v in source_data.items():
                if k not in merged and k not in ['_id', 'key', 'source']:
                    merged[k] = v
        
        return merged
    
    async def get_global_market(self) -> Dict[str, Any]:
        """Get global market data, prefer CoinGecko"""
        
        # CoinGecko latest
        cg_doc = await self.db.intel_market.find_one(
            {'key': 'coingecko:global:latest'}, 
            {'_id': 0}
        )
        
        # CryptoRank latest
        cr_doc = await self.db.intel_market.find_one(
            {'source': 'cryptorank'}, 
            {'_id': 0}
        )
        
        if not cg_doc and not cr_doc:
            return {}
        
        # Prefer CoinGecko, supplement with CryptoRank
        merged = cg_doc or {}
        if cr_doc:
            for k, v in cr_doc.items():
                if k not in merged or merged.get(k) is None:
                    merged[k] = v
        
        merged['sources'] = []
        if cg_doc:
            merged['sources'].append('coingecko')
        if cr_doc:
            merged['sources'].append('cryptorank')
        
        return merged
    
    async def search_projects(
        self, 
        query: str, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search projects and return aggregated results"""
        
        # Search in intel_projects
        cursor = self.db.intel_projects.find(
            {
                '$or': [
                    {'symbol': {'$regex': query, '$options': 'i'}},
                    {'name': {'$regex': query, '$options': 'i'}}
                ]
            },
            {'_id': 0, 'symbol': 1}
        ).limit(limit * 3)  # Get more to account for duplicates
        
        docs = await cursor.to_list(limit * 3)
        
        # Get unique symbols
        symbols = list(set(d['symbol'] for d in docs if d.get('symbol')))
        
        # Aggregate each
        results = []
        for symbol in symbols[:limit]:
            project = await self.get_project(symbol)
            if project:
                results.append(project)
        
        return results


# Factory
def create_data_aggregator(db):
    return DataAggregator(db)
