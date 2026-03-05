"""
Categories parser for CryptoRank
"""

from typing import Dict, List


def parse_categories(data: List[Dict]) -> List[Dict]:
    """
    Parse crypto categories from CryptoRank.
    
    Input format:
    {
        "id": 54,
        "name": "DeFi",
        "slug": "defi",
        "description": "..."
    }
    """
    results = []
    
    for cat in data:
        cat_id = cat.get('id')
        cat_name = cat.get('name')
        cat_slug = cat.get('slug')
        
        if not cat_name:
            continue
        
        # Use slug or create from name
        slug = cat_slug or cat_name.lower().replace(' ', '-')
        key = f"cryptorank:category:{slug}"
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': slug,
            'source_id': cat_id,
            
            'name': cat_name,
            'slug': slug,
            'description': cat.get('description'),
        }
        
        results.append(doc)
    
    return results
