"""
ClickHouse Store - Historical Candle Storage
Stage 7: Historical Data Layer
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from clickhouse_driver import Client

logger = logging.getLogger(__name__)


class ClickHouseStore:
    """
    ClickHouse client for historical candle storage.
    Handles OHLCV data with dedup via ReplacingMergeTree.
    """
    
    def __init__(self):
        self.host = os.environ.get('CLICKHOUSE_HOST', 'localhost')
        self.port = int(os.environ.get('CLICKHOUSE_PORT', 9000))
        self.database = os.environ.get('CLICKHOUSE_DATABASE', 'fomo')
        self.user = os.environ.get('CLICKHOUSE_USER', 'default')
        self.password = os.environ.get('CLICKHOUSE_PASSWORD', '')
        self._client: Optional[Client] = None
        self._connected = False
    
    def connect(self):
        """Connect to ClickHouse"""
        if self._connected:
            return
        
        try:
            self._client = Client(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            # Test connection
            self._client.execute("SELECT 1")
            self._connected = True
            logger.info(f"[ClickHouse] Connected to {self.host}:{self.port}/{self.database}")
        except Exception as e:
            logger.error(f"[ClickHouse] Connection failed: {e}")
            self._connected = False
            raise
    
    def disconnect(self):
        """Disconnect from ClickHouse"""
        if self._client:
            self._client.disconnect()
            self._connected = False
            logger.info("[ClickHouse] Disconnected")
    
    def ensure_connected(self):
        """Ensure connection is active"""
        if not self._connected:
            self.connect()
    
    # ═══════════════════════════════════════════════════════════════
    # CANDLE WRITE OPERATIONS
    # ═══════════════════════════════════════════════════════════════
    
    def insert_candles(self, candles: List[Dict[str, Any]]) -> int:
        """
        Batch insert candles.
        
        Each candle dict should have:
        - exchange: str
        - symbol: str
        - tf: str (1m, 5m, 15m, 1h, 4h, 1d, 1w)
        - ts: datetime or unix timestamp
        - open, high, low, close, volume: float
        """
        self.ensure_connected()
        
        if not candles:
            return 0
        
        # Prepare data for insert
        rows = []
        for c in candles:
            ts = c['ts']
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            
            rows.append({
                'exchange': c['exchange'],
                'symbol': c['symbol'],
                'tf': c['tf'],
                'ts': ts,
                'open': float(c['open']),
                'high': float(c['high']),
                'low': float(c['low']),
                'close': float(c['close']),
                'volume': float(c.get('volume', 0)),
                'version': int(datetime.now(timezone.utc).timestamp() * 1000)
            })
        
        try:
            self._client.execute(
                """
                INSERT INTO candles_ohlcv 
                (exchange, symbol, tf, ts, open, high, low, close, volume, version)
                VALUES
                """,
                rows
            )
            logger.debug(f"[ClickHouse] Inserted {len(rows)} candles")
            return len(rows)
        except Exception as e:
            logger.error(f"[ClickHouse] Insert failed: {e}")
            raise
    
    # ═══════════════════════════════════════════════════════════════
    # CANDLE READ OPERATIONS
    # ═══════════════════════════════════════════════════════════════
    
    def get_candles(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get candles for a symbol.
        Uses FINAL to get deduplicated results from ReplacingMergeTree.
        """
        self.ensure_connected()
        
        query = """
            SELECT 
                exchange, symbol, tf, ts,
                open, high, low, close, volume
            FROM candles_ohlcv FINAL
            WHERE exchange = %(exchange)s 
              AND symbol = %(symbol)s 
              AND tf = %(tf)s
        """
        
        params = {'exchange': exchange, 'symbol': symbol, 'tf': tf}
        
        if from_ts:
            query += " AND ts >= %(from_ts)s"
            params['from_ts'] = from_ts
        
        if to_ts:
            query += " AND ts <= %(to_ts)s"
            params['to_ts'] = to_ts
        
        query += " ORDER BY ts ASC LIMIT %(limit)s"
        params['limit'] = limit
        
        try:
            result = self._client.execute(query, params, with_column_types=True)
            rows, columns = result
            col_names = [c[0] for c in columns]
            
            candles = []
            for row in rows:
                candle = dict(zip(col_names, row))
                # Convert datetime to unix timestamp
                if isinstance(candle['ts'], datetime):
                    candle['ts'] = int(candle['ts'].timestamp())
                candles.append(candle)
            
            return candles
        except Exception as e:
            logger.error(f"[ClickHouse] Query failed: {e}")
            return []
    
    def get_latest_candle_ts(
        self,
        exchange: str,
        symbol: str,
        tf: str
    ) -> Optional[datetime]:
        """Get the timestamp of the latest candle"""
        self.ensure_connected()
        
        try:
            result = self._client.execute(
                """
                SELECT max(ts) as latest_ts
                FROM candles_ohlcv FINAL
                WHERE exchange = %(exchange)s 
                  AND symbol = %(symbol)s 
                  AND tf = %(tf)s
                """,
                {'exchange': exchange, 'symbol': symbol, 'tf': tf}
            )
            if result and result[0][0]:
                return result[0][0]
            return None
        except Exception as e:
            logger.error(f"[ClickHouse] Query latest ts failed: {e}")
            return None
    
    def count_candles(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        from_ts: Optional[datetime] = None
    ) -> int:
        """Count candles for a symbol"""
        self.ensure_connected()
        
        query = """
            SELECT count() 
            FROM candles_ohlcv FINAL
            WHERE exchange = %(exchange)s 
              AND symbol = %(symbol)s 
              AND tf = %(tf)s
        """
        params = {'exchange': exchange, 'symbol': symbol, 'tf': tf}
        
        if from_ts:
            query += " AND ts >= %(from_ts)s"
            params['from_ts'] = from_ts
        
        try:
            result = self._client.execute(query, params)
            return result[0][0] if result else 0
        except Exception as e:
            logger.error(f"[ClickHouse] Count failed: {e}")
            return 0
    
    # ═══════════════════════════════════════════════════════════════
    # INTEGRITY CHECKS
    # ═══════════════════════════════════════════════════════════════
    
    def check_continuity(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        expected_interval_seconds: int
    ) -> Dict[str, Any]:
        """
        Check if candles are continuous (no gaps).
        Returns gap info if any.
        """
        self.ensure_connected()
        
        try:
            # Get all timestamps
            result = self._client.execute(
                """
                SELECT ts
                FROM candles_ohlcv FINAL
                WHERE exchange = %(exchange)s 
                  AND symbol = %(symbol)s 
                  AND tf = %(tf)s
                ORDER BY ts ASC
                """,
                {'exchange': exchange, 'symbol': symbol, 'tf': tf}
            )
            
            timestamps = [r[0] for r in result]
            
            if len(timestamps) < 2:
                return {
                    'continuous': True,
                    'count': len(timestamps),
                    'gaps': []
                }
            
            gaps = []
            tolerance = expected_interval_seconds * 1.5  # Allow some tolerance
            
            for i in range(1, len(timestamps)):
                diff = (timestamps[i] - timestamps[i-1]).total_seconds()
                if diff > tolerance:
                    gaps.append({
                        'from': timestamps[i-1].isoformat(),
                        'to': timestamps[i].isoformat(),
                        'missing_seconds': int(diff - expected_interval_seconds)
                    })
            
            return {
                'continuous': len(gaps) == 0,
                'count': len(timestamps),
                'gaps': gaps[:10]  # Limit to first 10 gaps
            }
        except Exception as e:
            logger.error(f"[ClickHouse] Continuity check failed: {e}")
            return {'continuous': False, 'error': str(e)}
    
    def health_check(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        min_candles: int = 100,
        max_staleness_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Health check for a specific symbol/tf.
        Used by TA Engine to verify data quality.
        """
        self.ensure_connected()
        
        try:
            # Get count and latest ts
            result = self._client.execute(
                """
                SELECT 
                    count() as cnt,
                    max(ts) as latest_ts,
                    min(ts) as earliest_ts
                FROM candles_ohlcv FINAL
                WHERE exchange = %(exchange)s 
                  AND symbol = %(symbol)s 
                  AND tf = %(tf)s
                """,
                {'exchange': exchange, 'symbol': symbol, 'tf': tf}
            )
            
            if not result or result[0][0] == 0:
                return {
                    'healthy': False,
                    'reason': 'NO_DATA',
                    'count': 0
                }
            
            count, latest_ts, earliest_ts = result[0]
            
            # Check count
            if count < min_candles:
                return {
                    'healthy': False,
                    'reason': 'INSUFFICIENT_DATA',
                    'count': count,
                    'required': min_candles
                }
            
            # Check staleness
            now = datetime.now(timezone.utc)
            if latest_ts.tzinfo is None:
                latest_ts = latest_ts.replace(tzinfo=timezone.utc)
            
            staleness = (now - latest_ts).total_seconds()
            
            if staleness > max_staleness_seconds:
                return {
                    'healthy': False,
                    'reason': 'STALE_DATA',
                    'staleness_seconds': int(staleness),
                    'max_allowed': max_staleness_seconds,
                    'latest_ts': latest_ts.isoformat()
                }
            
            return {
                'healthy': True,
                'count': count,
                'latest_ts': latest_ts.isoformat(),
                'earliest_ts': earliest_ts.isoformat(),
                'staleness_seconds': int(staleness)
            }
        except Exception as e:
            logger.error(f"[ClickHouse] Health check failed: {e}")
            return {'healthy': False, 'reason': 'ERROR', 'error': str(e)}
    
    # ═══════════════════════════════════════════════════════════════
    # STATS
    # ═══════════════════════════════════════════════════════════════
    
    def stats(self) -> Dict[str, Any]:
        """Get overall statistics"""
        self.ensure_connected()
        
        try:
            result = self._client.execute(
                """
                SELECT 
                    count() as total_rows,
                    uniq(exchange) as exchanges,
                    uniq(symbol) as symbols,
                    uniq(tf) as timeframes,
                    min(ts) as earliest,
                    max(ts) as latest
                FROM candles_ohlcv
                """
            )
            
            row = result[0]
            return {
                'connected': True,
                'total_candles': row[0],
                'exchanges': row[1],
                'symbols': row[2],
                'timeframes': row[3],
                'earliest_ts': row[4].isoformat() if row[4] else None,
                'latest_ts': row[5].isoformat() if row[5] else None
            }
        except Exception as e:
            return {'connected': False, 'error': str(e)}
    
    def health(self) -> Dict[str, Any]:
        """Connection health check"""
        try:
            self.ensure_connected()
            result = self._client.execute("SELECT 1")
            return {'healthy': True, 'connected': True}
        except Exception as e:
            return {'healthy': False, 'error': str(e)}


# Singleton instance
clickhouse_store = ClickHouseStore()
