"""
Launchpads parser for CryptoRank
"""

from typing import Dict, List


def parse_launchpads(data: List[Dict]) -> List[Dict]:
    """
    Parse launchpads from CryptoRank.
    
    Input format:
    {
        "id": 46,
        "key": "seedify",
        "name": "Seedify",
        "icon": "...",
        "rank": 17,
        "type": "IDO"
    }
    """
    results = []
    
    for lp in data:
        lp_key = lp.get('key')
        lp_name = lp.get('name')
        
        if not lp_key or not lp_name:
            continue
        
        key = f"cryptorank:launchpad:{lp_key}"
        
        # Determine tier based on rank
        rank = lp.get('rank') or 999
        if rank <= 5:
            tier = 1
        elif rank <= 20:
            tier = 2
        else:
            tier = 3
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': lp_key,
            
            'name': lp_name,
            'slug': lp_key,
            'type': lp.get('type'),  # IDO, IEO, ICO
            
            # Ranking
            'rank': rank,
            'tier': tier,
            
            # Media
            'icon': lp.get('icon'),
        }
        
        results.append(doc)
    
    return results
