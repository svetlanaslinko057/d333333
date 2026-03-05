"""
Provider Adapter Interface
Контракт для всех провайдеров данных
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Any
from ..domain.types import (
    Venue, ProviderCapabilities,
    Ticker, OrderBook, Trade, Candle,
    FundingRate, FundingHistoryPoint, OpenInterest,
    LongShortRatio, Liquidation, MarkPrice, Instrument
)

class MarketDataProvider(ABC):
    """
    Абстрактный интерфейс провайдера рыночных данных.
    Все провайдеры (Binance, Bybit, Coinbase, Hyperliquid) реализуют этот контракт.
    """
    
    @property
    @abstractmethod
    def venue(self) -> Venue:
        """Идентификатор биржи"""
        pass
    
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Возвращает возможности провайдера"""
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # CORE MARKET DATA (обязательные)
    # ═══════════════════════════════════════════════════════════════
    
    @abstractmethod
    async def list_instruments(self, market_type: str) -> List[Instrument]:
        """Список торговых инструментов"""
        pass
    
    @abstractmethod
    async def get_ticker(self, native_symbol: str) -> Ticker:
        """Текущий тикер"""
        pass
    
    @abstractmethod
    async def get_orderbook(self, native_symbol: str, depth: int = 20) -> OrderBook:
        """Order book (L2)"""
        pass
    
    @abstractmethod
    async def get_trades(self, native_symbol: str, limit: int = 100) -> List[Trade]:
        """Последние сделки"""
        pass
    
    @abstractmethod
    async def get_candles(
        self, 
        native_symbol: str, 
        granularity: str = "1h",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[Candle]:
        """OHLCV свечи"""
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # DERIVATIVES (опциональные - проверять capabilities)
    # ═══════════════════════════════════════════════════════════════
    
    async def get_funding(self, native_symbol: str) -> Optional[FundingRate]:
        """Текущий funding rate"""
        return None
    
    async def get_funding_history(
        self, 
        native_symbol: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[FundingHistoryPoint]:
        """История funding rate"""
        return []
    
    async def get_open_interest(self, native_symbol: str) -> Optional[OpenInterest]:
        """Open Interest"""
        return None
    
    async def get_long_short_ratio(self, native_symbol: str) -> Optional[LongShortRatio]:
        """Long/Short ratio"""
        return None
    
    async def get_liquidations(self, native_symbol: str, limit: int = 100) -> List[Liquidation]:
        """Ликвидации"""
        return []
    
    async def get_mark_price(self, native_symbol: str) -> Optional[MarkPrice]:
        """Mark price + Index price"""
        return None
    
    async def get_agg_trades(self, native_symbol: str, limit: int = 100) -> List[Trade]:
        """Агрегированные сделки"""
        return []
    
    # ═══════════════════════════════════════════════════════════════
    # WEBSOCKET (опциональные)
    # ═══════════════════════════════════════════════════════════════
    
    async def connect_ws(self) -> None:
        """Подключение к WebSocket"""
        pass
    
    async def disconnect_ws(self) -> None:
        """Отключение от WebSocket"""
        pass
    
    async def subscribe_ws(self, channel: str, symbol: str) -> None:
        """Подписка на канал"""
        pass
    
    async def unsubscribe_ws(self, channel: str, symbol: str) -> None:
        """Отписка от канала"""
        pass
    
    def on_ws_message(self, callback: Callable[[Any], None]) -> None:
        """Установка callback для сообщений WS"""
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # HEALTH
    # ═══════════════════════════════════════════════════════════════
    
    async def health_check(self) -> dict:
        """Проверка здоровья провайдера"""
        return {
            "venue": self.venue.value,
            "healthy": True,
            "latency_ms": None,
            "error": None
        }
