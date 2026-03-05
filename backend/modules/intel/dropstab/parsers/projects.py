from typing import Optional
"""
Projects parser
"""

from typing import Dict, List, Any
from datetime import datetime


def parse_timestamp(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value < 1e12 else int(value / 1000)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return int(dt.timestamp())
        except:
            return None
    return None


def parse_projects(data: List[Dict]) -> List[Dict]:
    """
    Parse projects from Dropstab.
    """
    results = []
    
    for p in data:
        symbol = (p.get('symbol') or p.get('ticker') or '').upper()
        name = p.get('name') or p.get('projectName') or symbol
        
        if not symbol and not name:
            continue
        
        slug = p.get('slug') or (symbol.lower() if symbol else name.lower().replace(' ', '-'))
        
        # Create unique key
        key = f"dropstab:project:{slug}"
        
        doc = {
            'key': key,
            'source': 'dropstab',
            
            'name': name,
            'symbol': symbol,
            'slug': slug,
            
            'category': p.get('category') or p.get('sector'),
            'tags': p.get('tags') or [],
            
            'website': p.get('website') or p.get('url'),
            'twitter': p.get('twitter'),
            'discord': p.get('discord'),
            'telegram': p.get('telegram'),
            'github': p.get('github'),
            
            'logo_url': p.get('logo') or p.get('logoUrl') or p.get('image'),
            'description': p.get('description') or p.get('shortDescription'),
            
            'ico_date': parse_timestamp(p.get('icoDate') or p.get('launchDate')),
            'listing_date': parse_timestamp(p.get('listingDate')),
            
            'total_supply': p.get('totalSupply'),
            'circulating_supply': p.get('circulatingSupply'),
            'max_supply': p.get('maxSupply'),
            
            'raw': p
        }
        
        results.append(doc)
    
    return results
