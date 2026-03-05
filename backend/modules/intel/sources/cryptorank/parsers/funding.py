"""
Funding rounds parser for CryptoRank
Parses data from /v0/coins/funding-rounds endpoint
"""

from typing import Dict, List, Any, Optional
from datetime import datetime


def parse_timestamp(value: Any) -> Optional[int]:
    """Convert date string to unix timestamp"""
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
        try:
            for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S']:
                dt = datetime.strptime(value, fmt)
                return int(dt.timestamp())
        except:
            pass
    return None


def parse_funding(data: List[Dict]) -> List[Dict]:
    """
    Parse funding rounds from CryptoRank.
    
    Input format:
    {
        "key": "cyclops",
        "name": "Cyclops",
        "symbol": null,
        "icon": "...",
        "raise": 8000000,
        "stage": "STRATEGIC",
        "date": "2026-03-04",
        "funds": [
            {
                "key": "castle-island-ventures",
                "name": "Castle Island Ventures",
                "tier": 2,
                "type": "NORMAL",
                "category": {"name": "venture"},
                "totalInvestments": 48
            }
        ]
    }
    """
    results = []
    
    for r in data:
        project_key = r.get('key')
        project_name = r.get('name')
        
        if not project_key or not project_name:
            continue
        
        symbol = r.get('symbol') or ''
        stage = r.get('stage') or 'unknown'
        date = parse_timestamp(r.get('date'))
        
        # Create unique key
        date_str = r.get('date', 'nodate')
        key = f"cryptorank:funding:{project_key}-{stage}-{date_str}".lower()
        
        # Parse investors from funds array
        investors = []
        lead_investors = []
        
        for fund in (r.get('funds') or []):
            fund_name = fund.get('name')
            if not fund_name:
                continue
            
            inv = {
                'name': fund_name,
                'key': fund.get('key'),
                'tier': fund.get('tier'),
                'type': fund.get('type'),
                'category': fund.get('category', {}).get('name') if isinstance(fund.get('category'), dict) else None,
                'total_investments': fund.get('totalInvestments')
            }
            investors.append(inv)
            
            # Tier 1 investors are lead
            if fund.get('tier') == 1:
                lead_investors.append(fund_name)
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': project_key,
            
            # Project info
            'project': project_name,
            'project_key': project_key,
            'symbol': symbol.upper() if symbol else None,
            'icon': r.get('icon'),
            
            # Round details
            'round': stage,
            'date': date,
            
            # Amount
            'amount': r.get('raise'),
            
            # Investors
            'investors': investors,
            'investors_count': len(investors),
            'lead_investors': lead_investors,
            
            # Extra metadata
            'country': r.get('country'),
            'twitter_score': r.get('twitterScore'),
        }
        
        results.append(doc)
    
    return results
