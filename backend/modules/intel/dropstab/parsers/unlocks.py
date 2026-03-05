from typing import Optional
"""
Unlocks/Vesting parser
"""

from typing import Dict, List, Any
from datetime import datetime, timezone


def parse_timestamp(value: Any) -> Optional[int]:
    """Convert various date formats to unix timestamp"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Already timestamp (might be ms)
        return int(value) if value < 1e12 else int(value / 1000)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return int(dt.timestamp())
        except:
            return None
    return None


def parse_unlocks(data: List[Dict]) -> List[Dict]:
    """
    Parse token unlocks/vesting from Dropstab.
    """
    results = []
    
    for u in data:
        symbol = (u.get('symbol') or u.get('ticker') or '').upper()
        if not symbol:
            continue
        
        project = u.get('projectName') or u.get('name') or u.get('project') or symbol
        unlock_date = parse_timestamp(u.get('unlockDate') or u.get('date') or u.get('vestingDate'))
        
        if not unlock_date:
            continue
        
        category = (u.get('category') or u.get('type') or 'other').lower()
        
        # Create unique key
        key = f"dropstab:unlock:{symbol}:{unlock_date}:{category}"
        
        doc = {
            'key': key,
            'source': 'dropstab',
            
            'project': project,
            'symbol': symbol,
            
            'unlock_date': unlock_date,
            'unlock_amount': float(u.get('amount') or u.get('unlockAmount') or 0),
            'unlock_percent': float(u.get('percent') or u.get('unlockPercent') or u.get('percentage') or 0),
            'unlock_value_usd': u.get('valueUsd') or u.get('unlockValue'),
            
            'category': category,
            'description': u.get('description'),
            
            'raw': u
        }
        
        results.append(doc)
    
    return results
