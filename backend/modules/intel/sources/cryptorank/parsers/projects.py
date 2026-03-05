"""
Projects/Coins parser for CryptoRank
"""

from typing import Dict, List, Any, Optional
from datetime import datetime


def parse_timestamp(value: Any) -> Optional[int]:
    """Convert various date formats to unix timestamp"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value < 1e12 else int(value / 1000)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return int(dt.timestamp())
        except:
            pass
    return None


def parse_projects(data: List[Dict]) -> List[Dict]:
    """
    Parse projects/coins from CryptoRank.
    
    Expected input format (from /v1/currencies):
    {
        "key": "bitcoin",
        "name": "Bitcoin",
        "symbol": "BTC",
        "rank": 1,
        "category": {"key": "currency", "name": "Currency"},
        "tags": [{"key": "pow", "name": "PoW"}, ...],
        "price": {"USD": 65000},
        "marketCap": 1300000000000,
        "volume24h": 25000000000,
        "circulatingSupply": 19500000,
        "totalSupply": 21000000,
        "maxSupply": 21000000,
        "ath": {"USD": 73000, "date": "2024-03-14"},
        "atl": {"USD": 67, "date": "2013-07-05"},
        "percentChange24h": 2.5,
        "percentChange7d": -5.2,
        "percentChange30d": 15.3,
        "links": {...},
        "image": {...}
    }
    """
    results = []
    
    for c in data:
        symbol = (c.get('symbol') or '').upper()
        project_key = c.get('key')
        
        if not symbol or not project_key:
            continue
        
        key = f"cryptorank:project:{project_key}"
        
        # Parse category
        category = c.get('category') or {}
        category_name = category.get('name') if isinstance(category, dict) else None
        
        # Parse tags
        tags = []
        for tag in (c.get('tags') or []):
            if isinstance(tag, dict) and tag.get('name'):
                tags.append(tag['name'])
            elif isinstance(tag, str):
                tags.append(tag)
        
        # Parse price
        price_data = c.get('price') or {}
        price_usd = price_data.get('USD') if isinstance(price_data, dict) else None
        
        # Parse ATH/ATL
        ath = c.get('ath') or {}
        atl = c.get('atl') or {}
        
        # Parse links
        links = c.get('links') or {}
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': project_key,
            
            # Basic info
            'name': c.get('name'),
            'symbol': symbol,
            'slug': project_key,
            'rank': c.get('rank'),
            
            # Category & tags
            'category': category_name,
            'tags': tags,
            
            # Market data
            'price_usd': price_usd,
            'market_cap': c.get('marketCap'),
            'volume_24h': c.get('volume24h'),
            
            # Supply
            'circulating_supply': c.get('circulatingSupply'),
            'total_supply': c.get('totalSupply'),
            'max_supply': c.get('maxSupply'),
            
            # Price changes
            'change_24h': c.get('percentChange24h'),
            'change_7d': c.get('percentChange7d'),
            'change_30d': c.get('percentChange30d'),
            
            # ATH/ATL
            'ath_price': ath.get('USD') if isinstance(ath, dict) else None,
            'ath_date': parse_timestamp(ath.get('date')) if isinstance(ath, dict) else None,
            'atl_price': atl.get('USD') if isinstance(atl, dict) else None,
            'atl_date': parse_timestamp(atl.get('date')) if isinstance(atl, dict) else None,
            
            # Links
            'website': links.get('website') if isinstance(links, dict) else None,
            'twitter': links.get('twitter') if isinstance(links, dict) else None,
            'telegram': links.get('telegram') if isinstance(links, dict) else None,
            'github': links.get('github') if isinstance(links, dict) else None,
            
            # Image
            'image': c.get('image', {}).get('native') if isinstance(c.get('image'), dict) else None,
            
            'raw': c
        }
        
        results.append(doc)
    
    return results
