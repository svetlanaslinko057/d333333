"""
Investors parser for CryptoRank
"""

from typing import Dict, List


def parse_top_investors(data: List[Dict]) -> List[Dict]:
    """
    Parse top investors from CryptoRank.
    
    Input format:
    {
        "slug": "coinbase-ventures",
        "name": "Coinbase Ventures",
        "count": 38,
        "logo": "..."
    }
    """
    results = []
    
    for inv in data:
        slug = inv.get('slug')
        name = inv.get('name')
        
        if not slug or not name:
            continue
        
        key = f"cryptorank:investor:{slug}"
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': slug,
            
            'name': name,
            'slug': slug,
            
            # Activity stats
            'investments_count': inv.get('count', 0),
            
            # Media
            'logo': inv.get('logo'),
            'image': inv.get('logo'),
        }
        
        results.append(doc)
    
    return results


def parse_investors_from_funding(investors: List[Dict]) -> List[Dict]:
    """
    Parse detailed investor info from funding round data.
    
    Input format (from funding.funds[]):
    {
        "key": "castle-island-ventures",
        "name": "Castle Island Ventures",
        "tier": 2,
        "type": "NORMAL",
        "category": {"name": "venture"},
        "totalInvestments": 48,
        "image": "..."
    }
    """
    results = []
    
    for inv in investors:
        inv_key = inv.get('key')
        inv_name = inv.get('name')
        
        if not inv_key or not inv_name:
            continue
        
        key = f"cryptorank:investor:{inv_key}"
        
        category = inv.get('category')
        category_name = category.get('name') if isinstance(category, dict) else None
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': inv_key,
            
            'name': inv_name,
            'slug': inv_key,
            
            # Classification
            'tier': inv.get('tier'),
            'type': inv.get('type'),
            'category': category_name,
            
            # Stats
            'investments_count': inv.get('totalInvestments', 0),
            
            # Media
            'image': inv.get('image'),
        }
        
        results.append(doc)
    
    return results
