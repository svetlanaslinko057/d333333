"""
Token Unlocks parser for CryptoRank
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


def parse_unlocks(data: List[Dict]) -> List[Dict]:
    """
    Parse token unlocks from CryptoRank.
    
    Input format:
    {
        "key": "tribal",
        "symbol": "TRIBL",
        "unlockUsd": 29983890,
        "tokensPercent": 6.1,
        "unlockDate": "2026-03-04",
        "isHidden": false
    }
    """
    results = []
    
    for u in data:
        project_key = u.get('key')
        symbol = (u.get('symbol') or '').upper()
        
        # Skip if hidden and no data
        if u.get('isHidden') and not project_key:
            continue
        
        unlock_date = u.get('unlockDate')
        date_ts = parse_timestamp(unlock_date)
        
        if not unlock_date:
            continue
        
        # Create unique key
        key = f"cryptorank:unlock:{project_key or 'hidden'}-{unlock_date}"
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': project_key,
            
            # Project
            'project': u.get('name') or project_key,
            'project_key': project_key,
            'symbol': symbol if symbol else None,
            
            # Unlock details
            'unlock_date': date_ts,
            'unlock_date_str': unlock_date,
            'unlock_value_usd': u.get('unlockUsd'),
            'unlock_percent': u.get('tokensPercent'),
            
            # Type
            'unlock_type': 'vesting',
            
            # Hidden flag
            'is_hidden': u.get('isHidden', False),
        }
        
        results.append(doc)
    
    return results


def parse_tge_unlocks(data: List[Dict]) -> List[Dict]:
    """
    Parse TGE (Token Generation Event) unlocks from CryptoRank.
    
    Input format:
    {
        "key": "hyperlend",
        "symbol": "HPL",
        "unlockTokens": 17360000,
        "unlockPercent": 1.7,
        "tgeDate": "2026-02-26",
        "isHidden": false
    }
    """
    results = []
    
    for u in data:
        project_key = u.get('key')
        symbol = (u.get('symbol') or '').upper()
        
        if u.get('isHidden') and not project_key:
            continue
        
        tge_date = u.get('tgeDate')
        date_ts = parse_timestamp(tge_date)
        
        if not tge_date:
            continue
        
        key = f"cryptorank:tge:{project_key or 'hidden'}-{tge_date}"
        
        doc = {
            'key': key,
            'source': 'cryptorank',
            'source_key': project_key,
            
            # Project
            'project': u.get('name') or project_key,
            'project_key': project_key,
            'symbol': symbol if symbol else None,
            
            # TGE details
            'unlock_date': date_ts,
            'unlock_date_str': tge_date,
            'unlock_amount': u.get('unlockTokens'),
            'unlock_percent': u.get('unlockPercent'),
            
            # Type
            'unlock_type': 'tge',
            
            # Hidden flag
            'is_hidden': u.get('isHidden', False),
        }
        
        results.append(doc)
    
    return results
