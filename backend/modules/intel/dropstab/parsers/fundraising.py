from typing import Optional
"""
Fundraising/Funding rounds parser
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


def parse_fundraising(data: List[Dict]) -> List[Dict]:
    """
    Parse funding rounds from Dropstab.
    """
    results = []
    
    for r in data:
        symbol = (r.get('symbol') or r.get('ticker') or '').upper()
        if not symbol:
            continue
        
        project = r.get('projectName') or r.get('name') or r.get('project') or symbol
        round_name = r.get('round') or r.get('roundName') or r.get('stage') or 'unknown'
        date = parse_timestamp(r.get('date') or r.get('fundingDate') or r.get('announcedDate'))
        
        # Create unique key
        key = f"dropstab:funding:{symbol}:{round_name}:{date or 'nodate'}"
        
        # Parse investors list
        investors = []
        inv_data = r.get('investors') or r.get('leadInvestors') or []
        if isinstance(inv_data, list):
            for inv in inv_data:
                if isinstance(inv, str):
                    investors.append(inv)
                elif isinstance(inv, dict):
                    investors.append(inv.get('name') or inv.get('fundName') or str(inv))
        
        doc = {
            'key': key,
            'source': 'dropstab',
            
            'project': project,
            'symbol': symbol,
            
            'round': round_name,
            'date': date,
            
            'amount': r.get('amount') or r.get('raised') or r.get('fundingAmount'),
            'valuation': r.get('valuation') or r.get('postValuation'),
            
            'investors': investors,
            'lead_investor': r.get('leadInvestor') or (investors[0] if investors else None),
            
            'raw': r
        }
        
        results.append(doc)
    
    return results
