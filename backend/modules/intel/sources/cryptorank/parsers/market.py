"""
Market overview parser for CryptoRank
"""

from typing import Dict, Any
from datetime import datetime, timezone


def parse_market(data: Dict[str, Any]) -> Dict:
    """
    Parse market overview data from CryptoRank.
    
    Input format:
    {
        "btcDominance": 56.97,
        "ethDominance": 10.08,
        "totalMarketCap": 2563526299439,
        "totalVolume24h": 123456789,
        "gas": {
            "low": {"gasPriceGwei": 5},
            "average": {"gasPriceGwei": 10},
            "high": {"gasPriceGwei": 20}
        }
    }
    """
    gas = data.get('gas', {})
    
    return {
        'source': 'cryptorank',
        'timestamp': int(datetime.now(timezone.utc).timestamp()),
        
        # Dominance
        'btc_dominance': data.get('btcDominance'),
        'eth_dominance': data.get('ethDominance'),
        
        # Market metrics
        'total_market_cap': data.get('totalMarketCap'),
        'total_volume_24h': data.get('totalVolume24h'),
        
        # Gas prices (ETH)
        'gas_low': gas.get('low', {}).get('gasPriceGwei') if isinstance(gas, dict) else None,
        'gas_avg': gas.get('average', {}).get('gasPriceGwei') if isinstance(gas, dict) else None,
        'gas_high': gas.get('high', {}).get('gasPriceGwei') if isinstance(gas, dict) else None,
    }
