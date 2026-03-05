"""
Investors parser
"""

from typing import Dict, List, Any, Optional


def parse_investors(data: List[Dict]) -> List[Dict]:
    """
    Parse investors/VCs from Dropstab.
    Returns normalized documents.
    """
    results = []
    
    for x in data:
        name = x.get('name') or x.get('title') or x.get('fundName') or 'unknown'
        slug = x.get('slug') or x.get('id') or name.lower().replace(' ', '-')
        
        doc = {
            'key': f"dropstab:investor:{slug}",
            'source': 'dropstab',
            
            'name': name,
            'slug': slug,
            'tier': x.get('tier'),
            
            'website': x.get('website'),
            'twitter': x.get('twitter'),
            'linkedin': x.get('linkedin'),
            
            'investments_count': x.get('investmentsCount') or x.get('investments') or 0,
            'portfolio_value': x.get('portfolioValue'),
            
            'logo_url': x.get('logo') or x.get('logoUrl') or x.get('image'),
            'description': x.get('description') or x.get('bio'),
            
            'raw': x
        }
        
        results.append(doc)
    
    return results
