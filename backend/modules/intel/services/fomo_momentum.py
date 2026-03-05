"""
FOMO Momentum Index (FMI) Calculator

Branded trend detection index combining:
1. Volume Spike (40%)
2. Liquidity Inflow (30%)
3. Narrative Growth (20%)
4. Listing Signal (10%)

Score interpretation:
- 0-40: Low momentum (Calm)
- 40-60: Building momentum
- 60-80: Trending
- 80-100: FOMO Zone

Pre-computed every 5 minutes, stored in DB for instant API access.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# FMI STATE THRESHOLDS
# ═══════════════════════════════════════════════════════════════

FMI_STATES = {
    'CALM': (0, 40),
    'BUILDING': (40, 60),
    'TRENDING': (60, 80),
    'FOMO': (80, 100)
}


def get_fmi_state(score: float) -> str:
    """Get FMI state label from score"""
    if score >= 80:
        return 'FOMO'
    elif score >= 60:
        return 'TRENDING'
    elif score >= 40:
        return 'BUILDING'
    return 'CALM'


# ═══════════════════════════════════════════════════════════════
# FMI COMPONENT WEIGHTS
# ═══════════════════════════════════════════════════════════════

WEIGHTS = {
    'volume_spike': 0.4,
    'liquidity_inflow': 0.3,
    'narrative_growth': 0.2,
    'listing_signal': 0.1
}

# Listing score values
LISTING_SCORES = {
    'binance': 30,
    'coinbase': 30,
    'bybit': 25,
    'okx': 25,
    'kraken': 20,
    'kucoin': 15,
    'gate': 15,
    'bitget': 10,
    'mexc': 10,
    'other_cex': 5,
    'dex': 3
}


class FomoMomentumCalculator:
    """
    Calculator for FOMO Momentum Index (FMI)
    
    Usage:
        calc = FomoMomentumCalculator(db)
        
        # Calculate for single project
        fmi = await calc.calculate_fmi('ETH')
        
        # Pre-compute all (for scheduler)
        await calc.compute_all()
        
        # Get from DB (fast read)
        fmi = await calc.get_fmi('ETH')
        all_fmi = await calc.get_all_fmi()
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.fomo_momentum
    
    # ═══════════════════════════════════════════════════════════════
    # COMPONENT CALCULATORS
    # ═══════════════════════════════════════════════════════════════
    
    def _calculate_volume_spike(self, volume_24h: float, avg_volume_7d: float) -> Dict[str, Any]:
        """
        Volume Spike Score (0-100)
        
        Formula: volume_ratio = volume_24h / avg_volume_7d
        
        Score mapping:
        - ratio < 1: 0-20 points
        - ratio 1-2: 20-40 points
        - ratio 2-3: 40-60 points
        - ratio 3-5: 60-80 points
        - ratio > 5: 80-100 points
        """
        if not avg_volume_7d or avg_volume_7d <= 0:
            return {'score': 0, 'ratio': 0, 'volume_24h': volume_24h, 'avg_volume_7d': 0}
        
        ratio = volume_24h / avg_volume_7d
        
        # Map ratio to score (0-100)
        if ratio < 1:
            score = ratio * 20
        elif ratio < 2:
            score = 20 + (ratio - 1) * 20
        elif ratio < 3:
            score = 40 + (ratio - 2) * 20
        elif ratio < 5:
            score = 60 + (ratio - 3) * 10
        else:
            score = min(80 + (ratio - 5) * 4, 100)
        
        return {
            'score': round(score, 2),
            'ratio': round(ratio, 2),
            'volume_24h': volume_24h,
            'avg_volume_7d': avg_volume_7d
        }
    
    def _calculate_liquidity_inflow(self, marketcap_change_24h: float, marketcap: float) -> Dict[str, Any]:
        """
        Liquidity Inflow Score (0-100)
        
        Based on 24h marketcap change percentage
        
        Score mapping:
        - change < 0: 0-20 points
        - change 0-5%: 20-40 points  
        - change 5-15%: 40-60 points
        - change 15-30%: 60-80 points
        - change > 30%: 80-100 points
        """
        if marketcap_change_24h is None:
            marketcap_change_24h = 0
        
        change = marketcap_change_24h
        
        if change < 0:
            # Negative change, still give some score for recent activity
            score = max(0, 10 + change)  # -10% = 0, 0% = 10
        elif change < 5:
            score = 20 + (change / 5) * 20
        elif change < 15:
            score = 40 + ((change - 5) / 10) * 20
        elif change < 30:
            score = 60 + ((change - 15) / 15) * 20
        else:
            score = min(80 + (change - 30) / 10 * 20, 100)
        
        return {
            'score': round(score, 2),
            'marketcap_change_24h': round(marketcap_change_24h, 2),
            'marketcap': marketcap
        }
    
    def _calculate_narrative_growth(
        self, 
        sector: str, 
        sector_change_24h: float, 
        market_change_24h: float
    ) -> Dict[str, Any]:
        """
        Narrative Growth Score (0-100)
        
        Formula: sector_growth = sector_change_24h - market_change_24h
        
        Score mapping:
        - growth < 0: 0-20 points
        - growth 0-5%: 20-40 points
        - growth 5-10%: 40-60 points
        - growth 10-20%: 60-80 points
        - growth > 20%: 80-100 points
        """
        if sector_change_24h is None:
            sector_change_24h = 0
        if market_change_24h is None:
            market_change_24h = 0
        
        growth = sector_change_24h - market_change_24h
        
        if growth < 0:
            score = max(0, 10 + growth * 2)
        elif growth < 5:
            score = 20 + (growth / 5) * 20
        elif growth < 10:
            score = 40 + ((growth - 5) / 5) * 20
        elif growth < 20:
            score = 60 + ((growth - 10) / 10) * 20
        else:
            score = min(80 + (growth - 20) / 5 * 20, 100)
        
        return {
            'score': round(score, 2),
            'sector': sector or 'Unknown',
            'sector_growth_24h': round(growth, 2)
        }
    
    def _calculate_listing_signal(self, recent_listings: List[Dict]) -> Dict[str, Any]:
        """
        Listing Signal Score (0-100)
        
        Based on recent exchange listings (last 7 days)
        
        Score:
        - Binance/Coinbase: +30
        - Bybit/OKX: +25
        - Kraken: +20
        - Tier2 CEX: +15
        - Tier3 CEX: +10
        - DEX: +5
        
        Max score: 100
        """
        if not recent_listings:
            return {'score': 0, 'recent_listings': []}
        
        total_score = 0
        processed_listings = []
        
        for listing in recent_listings[:5]:  # Max 5 listings
            exchange = str(listing.get('exchange', '')).lower()
            
            # Find matching score
            points = 0
            for ex_name, ex_score in LISTING_SCORES.items():
                if ex_name in exchange:
                    points = ex_score
                    break
            
            if points == 0:
                if 'dex' in exchange or 'swap' in exchange or 'uni' in exchange:
                    points = LISTING_SCORES['dex']
                else:
                    points = LISTING_SCORES['other_cex']
            
            total_score += points
            processed_listings.append({
                'exchange': listing.get('exchange'),
                'pair': listing.get('pair'),
                'date': listing.get('date'),
                'points': points
            })
        
        return {
            'score': min(total_score, 100),
            'recent_listings': processed_listings
        }
    
    # ═══════════════════════════════════════════════════════════════
    # MAIN FMI CALCULATION
    # ═══════════════════════════════════════════════════════════════
    
    async def calculate_fmi(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Calculate FOMO Momentum Index for a single project
        
        Returns full FMI object with all components
        """
        symbol = symbol.upper()
        
        # Get project data - prefer dropstab, fallback to coingecko
        project = await self.db.intel_projects.find_one(
            {'symbol': symbol, 'source': 'dropstab'},
            {'_id': 0}
        )
        
        if not project:
            project = await self.db.intel_projects.find_one(
                {'symbol': symbol},
                {'_id': 0}
            )
        
        if not project:
            logger.warning(f"[FMI] Project not found: {symbol}")
            return None
        
        # Get historical data for avg_volume_7d
        # For now, use current volume as estimate (will be improved with historical data)
        volume_24h = project.get('total_volume', 0) or 0
        avg_volume_7d = volume_24h * 0.8  # Placeholder - should come from historical data
        
        # Get market change
        marketcap_change = project.get('price_change_percentage_24h', 0) or 0
        marketcap = project.get('market_cap', 0) or 0
        
        # Get sector/category data
        sector = project.get('category') or project.get('sector') or 'Unknown'
        
        # Get sector average change (placeholder)
        sector_change = marketcap_change * 1.1  # Placeholder
        market_change = 0  # Should come from global market data
        
        # Get recent listings
        recent_listings = await self.db.intel_activity.find(
            {
                'symbol': symbol,
                'type': {'$in': ['listing', 'activity']}
            },
            {'_id': 0}
        ).sort('date', -1).limit(5).to_list(5)
        
        # Calculate components
        volume_spike = self._calculate_volume_spike(volume_24h, avg_volume_7d)
        liquidity = self._calculate_liquidity_inflow(marketcap_change, marketcap)
        narrative = self._calculate_narrative_growth(sector, sector_change, market_change)
        listing = self._calculate_listing_signal(recent_listings)
        
        # Calculate final FMI score
        fmi_score = (
            volume_spike['score'] * WEIGHTS['volume_spike'] +
            liquidity['score'] * WEIGHTS['liquidity_inflow'] +
            narrative['score'] * WEIGHTS['narrative_growth'] +
            listing['score'] * WEIGHTS['listing_signal']
        )
        
        # Determine signals
        signals = []
        if volume_spike['ratio'] >= 2.5:
            signals.append('VOLUME_ANOMALY')
        if liquidity['marketcap_change_24h'] >= 15:
            signals.append('LIQUIDITY_SURGE')
        if narrative['sector_growth_24h'] >= 10:
            signals.append('SECTOR_MOMENTUM')
        if listing['score'] >= 25:
            signals.append('CEX_LISTING')
        
        return {
            'symbol': symbol,
            'timestamp': int(datetime.now(timezone.utc).timestamp()),
            'fmi': round(fmi_score, 2),
            'state': get_fmi_state(fmi_score),
            'components': {
                'volume_spike': volume_spike,
                'liquidity_inflow': liquidity,
                'narrative_growth': narrative,
                'listing_signal': listing
            },
            'signals': signals,
            'name': project.get('name', ''),
            'price_usd': project.get('price_usd'),
            'market_cap': marketcap,
            'sector': sector,
            'updated_at': datetime.now(timezone.utc)
        }
    
    async def compute_all(self, limit: int = 500) -> Dict[str, Any]:
        """
        Pre-compute FMI for all projects
        
        Run this every 5 minutes via scheduler
        """
        logger.info(f"[FMI] Starting pre-computation (limit={limit})...")
        
        # Get unique symbols with volume data
        # Use aggregation to get distinct symbols
        pipeline = [
            {'$match': {'total_volume': {'$gt': 0}}},
            {'$group': {'_id': '$symbol'}},
            {'$limit': limit}
        ]
        
        symbols_cursor = self.db.intel_projects.aggregate(pipeline)
        symbols = [doc['_id'] for doc in await symbols_cursor.to_list(limit)]
        
        computed = 0
        errors = 0
        
        for symbol in symbols:
            if not symbol:
                continue
            
            try:
                fmi = await self.calculate_fmi(symbol)
                if fmi:
                    # Store in DB
                    await self.collection.update_one(
                        {'symbol': symbol},
                        {'$set': fmi},
                        upsert=True
                    )
                    computed += 1
            except Exception as e:
                logger.error(f"[FMI] Error computing {symbol}: {e}")
                errors += 1
        
        logger.info(f"[FMI] Pre-computation complete: {computed} computed, {errors} errors")
        return {
            'computed': computed,
            'errors': errors,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    # ═══════════════════════════════════════════════════════════════
    # READ FROM DB (Fast)
    # ═══════════════════════════════════════════════════════════════
    
    async def get_fmi(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get pre-computed FMI for symbol"""
        return await self.collection.find_one(
            {'symbol': symbol.upper()},
            {'_id': 0}
        )
    
    async def get_all_fmi(
        self, 
        state: Optional[str] = None,
        min_fmi: Optional[float] = None,
        sector: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all FMI scores
        
        Args:
            state: Filter by state (CALM, BUILDING, TRENDING, FOMO)
            min_fmi: Minimum FMI score
            sector: Filter by sector
            limit: Max results
            offset: Pagination offset
        """
        query = {}
        
        if state:
            query['state'] = state.upper()
        if min_fmi is not None:
            query['fmi'] = {'$gte': min_fmi}
        if sector:
            query['sector'] = {'$regex': sector, '$options': 'i'}
        
        cursor = self.collection.find(query, {'_id': 0})
        items = await cursor.sort('fmi', -1).skip(offset).limit(limit).to_list(limit)
        
        return items
    
    async def get_trending(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get trending tokens (FMI >= 60)"""
        return await self.get_all_fmi(min_fmi=60, limit=limit)
    
    async def get_fomo_zone(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get tokens in FOMO zone (FMI >= 80)"""
        return await self.get_all_fmi(state='FOMO', limit=limit)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get FMI statistics"""
        total = await self.collection.count_documents({})
        
        # Count by state
        states = {}
        for state in FMI_STATES.keys():
            states[state] = await self.collection.count_documents({'state': state})
        
        # Top sectors
        pipeline = [
            {'$group': {'_id': '$sector', 'count': {'$sum': 1}, 'avg_fmi': {'$avg': '$fmi'}}},
            {'$sort': {'avg_fmi': -1}},
            {'$limit': 10}
        ]
        sectors = await self.collection.aggregate(pipeline).to_list(10)
        
        return {
            'total': total,
            'by_state': states,
            'top_sectors': sectors,
            'last_computed': datetime.now(timezone.utc).isoformat()
        }


# Factory function
def create_fmi_calculator(db: AsyncIOMotorDatabase) -> FomoMomentumCalculator:
    return FomoMomentumCalculator(db)
