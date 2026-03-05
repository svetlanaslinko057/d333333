"""
FOMO Momentum Index (FMI) Calculator

Trend detection formula:
FMI = Volume Spike (40%) + Liquidity Inflow (30%) + Narrative Growth (20%) + Listing Signal (10%)

States:
- 0-40: CALM
- 40-60: BUILDING
- 60-80: TRENDING
- 80-100: FOMO
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


def get_fmi_state(fmi: float) -> str:
    """Get FMI state label"""
    if fmi >= 80:
        return "FOMO"
    elif fmi >= 60:
        return "TRENDING"
    elif fmi >= 40:
        return "BUILDING"
    else:
        return "CALM"


class FMICalculator:
    """
    FOMO Momentum Index Calculator
    
    Pre-computes FMI for all tokens and stores in DB.
    API reads from DB for instant response.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # Weights for each component
        self.weights = {
            'volume_spike': 0.40,
            'liquidity_inflow': 0.30,
            'narrative_growth': 0.20,
            'listing_signal': 0.10
        }
        
        # Thresholds
        self.volume_spike_threshold = 2.5  # ratio > 2.5 = anomaly
        self.liquidity_threshold = 15.0  # >15% = significant
        self.narrative_threshold = 10.0  # >10% vs market = trend
    
    async def calculate_all(self) -> Dict[str, Any]:
        """
        Calculate FMI for all tokens in intel_projects
        Stores results in fomo_momentum collection
        """
        logger.info("[FMI] Starting calculation for all tokens...")
        
        # Get all projects with market data
        projects = await self.db.intel_projects.find(
            {'price_usd': {'$ne': None}},
            {'_id': 0}
        ).to_list(5000)
        
        if not projects:
            return {'calculated': 0, 'error': 'No projects with price data'}
        
        # Get market average for narrative comparison
        market_avg_change = await self._get_market_avg_change()
        
        # Get category performance
        category_performance = await self._get_category_performance()
        
        # Get recent listings
        recent_listings = await self._get_recent_listings()
        
        calculated = 0
        results = []
        
        for project in projects:
            try:
                fmi_data = await self._calculate_single(
                    project, 
                    market_avg_change, 
                    category_performance,
                    recent_listings
                )
                
                if fmi_data:
                    # Store in DB
                    await self.db.fomo_momentum.update_one(
                        {'symbol': fmi_data['symbol']},
                        {'$set': fmi_data},
                        upsert=True
                    )
                    calculated += 1
                    results.append({
                        'symbol': fmi_data['symbol'],
                        'fmi': fmi_data['fmi'],
                        'state': fmi_data['state']
                    })
                    
            except Exception as e:
                logger.error(f"[FMI] Error calculating {project.get('symbol')}: {e}")
        
        # Sort by FMI descending
        results.sort(key=lambda x: x['fmi'], reverse=True)
        
        logger.info(f"[FMI] Calculated {calculated} tokens")
        return {
            'calculated': calculated,
            'top_trending': results[:10],
            'ts': int(datetime.now(timezone.utc).timestamp() * 1000)
        }
    
    async def _calculate_single(
        self, 
        project: Dict,
        market_avg_change: float,
        category_performance: Dict[str, float],
        recent_listings: Dict[str, List]
    ) -> Optional[Dict]:
        """Calculate FMI for single token"""
        
        symbol = project.get('symbol', '').upper()
        if not symbol:
            return None
        
        # ═══════════════════════════════════════════════════════════
        # 1. VOLUME SPIKE (max 100 points)
        # ═══════════════════════════════════════════════════════════
        volume_24h = project.get('total_volume') or 0
        # Estimate avg volume (use current as baseline if no history)
        avg_volume_7d = volume_24h * 0.8  # Assume slight growth
        
        volume_ratio = volume_24h / avg_volume_7d if avg_volume_7d > 0 else 1.0
        
        # Score: ratio of 1 = 0, ratio of 5+ = 100
        if volume_ratio >= 5:
            volume_spike_score = 100
        elif volume_ratio >= self.volume_spike_threshold:
            volume_spike_score = min(100, (volume_ratio - 1) * 25)
        else:
            volume_spike_score = max(0, (volume_ratio - 1) * 20)
        
        # ═══════════════════════════════════════════════════════════
        # 2. LIQUIDITY INFLOW (max 100 points)
        # ═══════════════════════════════════════════════════════════
        change_24h = project.get('price_change_percentage_24h') or 0
        market_cap = project.get('market_cap') or 0
        
        # Score based on price change (proxy for liquidity inflow)
        if change_24h >= 50:
            liquidity_score = 100
        elif change_24h >= self.liquidity_threshold:
            liquidity_score = min(100, change_24h * 2)
        elif change_24h > 0:
            liquidity_score = change_24h * 1.5
        else:
            liquidity_score = max(0, 20 + change_24h)  # Negative change reduces score
        
        # ═══════════════════════════════════════════════════════════
        # 3. NARRATIVE GROWTH (max 100 points)
        # ═══════════════════════════════════════════════════════════
        sector = project.get('category') or project.get('sector') or 'Unknown'
        sector_growth = category_performance.get(sector, 0)
        
        # Compare to market average
        narrative_delta = sector_growth - market_avg_change
        
        if narrative_delta >= 20:
            narrative_score = 100
        elif narrative_delta >= self.narrative_threshold:
            narrative_score = min(100, 50 + narrative_delta * 2.5)
        elif narrative_delta > 0:
            narrative_score = 30 + narrative_delta * 2
        else:
            narrative_score = max(0, 30 + narrative_delta)
        
        # ═══════════════════════════════════════════════════════════
        # 4. LISTING SIGNAL (max 100 points)
        # ═══════════════════════════════════════════════════════════
        symbol_listings = recent_listings.get(symbol, [])
        
        listing_score = 0
        listing_details = []
        
        for listing in symbol_listings:
            exchange = listing.get('exchange', '').lower()
            # Tier 1 exchanges
            if any(t1 in exchange for t1 in ['binance', 'coinbase', 'kraken']):
                listing_score += 30
            # Tier 2 exchanges
            elif any(t2 in exchange for t2 in ['bybit', 'okx', 'kucoin', 'gate']):
                listing_score += 15
            # Other
            else:
                listing_score += 5
            
            listing_details.append({
                'exchange': listing.get('exchange'),
                'pair': listing.get('pair'),
                'date': listing.get('listing_date')
            })
        
        listing_score = min(100, listing_score)
        
        # ═══════════════════════════════════════════════════════════
        # CALCULATE FINAL FMI
        # ═══════════════════════════════════════════════════════════
        fmi = (
            volume_spike_score * self.weights['volume_spike'] +
            liquidity_score * self.weights['liquidity_inflow'] +
            narrative_score * self.weights['narrative_growth'] +
            listing_score * self.weights['listing_signal']
        )
        
        fmi = round(min(100, max(0, fmi)), 1)
        state = get_fmi_state(fmi)
        
        # Build signals list
        signals = []
        if volume_ratio >= self.volume_spike_threshold:
            signals.append('VOLUME_ANOMALY')
        if change_24h >= self.liquidity_threshold:
            signals.append('LIQUIDITY_SURGE')
        if narrative_delta >= self.narrative_threshold:
            signals.append('SECTOR_MOMENTUM')
        if listing_score > 0:
            signals.append('CEX_LISTING')
        
        return {
            'symbol': symbol,
            'slug': project.get('slug', symbol.lower()),
            'name': project.get('name', ''),
            'image': project.get('image'),
            
            'fmi': fmi,
            'state': state,
            
            'components': {
                'volumeSpike': {
                    'score': round(volume_spike_score * self.weights['volume_spike'], 1),
                    'ratio': round(volume_ratio, 2),
                    'volume24h': volume_24h
                },
                'liquidityInflow': {
                    'score': round(liquidity_score * self.weights['liquidity_inflow'], 1),
                    'marketcapChange24h': round(change_24h, 2),
                    'marketcap': market_cap
                },
                'narrativeGrowth': {
                    'score': round(narrative_score * self.weights['narrative_growth'], 1),
                    'sector': sector,
                    'sectorGrowth24h': round(sector_growth, 2)
                },
                'listingSignal': {
                    'score': round(listing_score * self.weights['listing_signal'], 1),
                    'recentListings': listing_details[:5]
                }
            },
            
            'signals': signals,
            'rank': project.get('market_cap_rank'),
            
            'updated_at': datetime.now(timezone.utc)
        }
    
    async def _get_market_avg_change(self) -> float:
        """Get average market change (top 100 by mcap)"""
        pipeline = [
            {'$match': {'price_change_percentage_24h': {'$ne': None}}},
            {'$sort': {'market_cap': -1}},
            {'$limit': 100},
            {'$group': {
                '_id': None,
                'avg_change': {'$avg': '$price_change_percentage_24h'}
            }}
        ]
        
        result = await self.db.intel_projects.aggregate(pipeline).to_list(1)
        return result[0]['avg_change'] if result else 0
    
    async def _get_category_performance(self) -> Dict[str, float]:
        """Get average performance by category/sector"""
        pipeline = [
            {'$match': {
                'price_change_percentage_24h': {'$ne': None},
                '$or': [
                    {'category': {'$ne': None}},
                    {'sector': {'$ne': None}}
                ]
            }},
            {'$group': {
                '_id': {'$ifNull': ['$category', '$sector']},
                'avg_change': {'$avg': '$price_change_percentage_24h'},
                'count': {'$sum': 1}
            }},
            {'$match': {'count': {'$gte': 3}}}  # At least 3 tokens
        ]
        
        result = await self.db.intel_projects.aggregate(pipeline).to_list(100)
        return {r['_id']: r['avg_change'] for r in result if r['_id']}
    
    async def _get_recent_listings(self) -> Dict[str, List]:
        """Get listings from last 7 days"""
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        cursor = self.db.intel_activity.find({
            'type': 'listing',
            'updated_at': {'$gte': week_ago}
        }, {'_id': 0})
        
        listings = await cursor.to_list(500)
        
        # Group by symbol
        by_symbol = {}
        for listing in listings:
            symbol = listing.get('symbol') or listing.get('coin_symbol', '').upper()
            if symbol:
                if symbol not in by_symbol:
                    by_symbol[symbol] = []
                by_symbol[symbol].append(listing)
        
        return by_symbol
    
    async def get_fmi(self, symbol: str) -> Optional[Dict]:
        """Get pre-computed FMI for symbol"""
        doc = await self.db.fomo_momentum.find_one(
            {'symbol': symbol.upper()},
            {'_id': 0}
        )
        return doc
    
    async def get_top_fmi(self, limit: int = 50, state: Optional[str] = None) -> List[Dict]:
        """Get top tokens by FMI"""
        query = {}
        if state:
            query['state'] = state.upper()
        
        cursor = self.db.fomo_momentum.find(query, {'_id': 0})
        cursor = cursor.sort('fmi', -1).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def get_trending(self) -> List[Dict]:
        """Get tokens in TRENDING or FOMO state"""
        cursor = self.db.fomo_momentum.find(
            {'state': {'$in': ['TRENDING', 'FOMO']}},
            {'_id': 0, 'symbol': 1, 'name': 1, 'fmi': 1, 'state': 1, 'signals': 1}
        )
        cursor = cursor.sort('fmi', -1).limit(100)
        
        return await cursor.to_list(100)


def create_fmi_calculator(db):
    return FMICalculator(db)
