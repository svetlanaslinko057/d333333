"""
Provider Registry
Централизованное управление всеми провайдерами
"""

from typing import Dict, List, Optional
from ..domain.types import Venue, ProviderCapabilities
from .base import MarketDataProvider
from .binance.adapter import binance_adapter
from .bybit.adapter import bybit_adapter
from .coinbase.adapter import coinbase_adapter
from .hyperliquid.adapter import hyperliquid_adapter

class ProviderRegistry:
    """
    Реестр провайдеров данных.
    Управляет доступом к провайдерам, их приоритетами и здоровьем.
    """
    
    def __init__(self):
        self._providers: Dict[Venue, MarketDataProvider] = {}
        self._priorities: Dict[Venue, int] = {}
        self._enabled: Dict[Venue, bool] = {}
        
        # Регистрируем все провайдеры
        self._register_defaults()
    
    def _register_defaults(self):
        """Регистрирует провайдеры по умолчанию"""
        # Bybit - primary (лучшая доступность)
        self.register(bybit_adapter, priority=100, enabled=True)
        
        # Binance - secondary (может быть заблокирован)
        self.register(binance_adapter, priority=90, enabled=True)
        
        # Hyperliquid - для derivatives + whale tracking
        self.register(hyperliquid_adapter, priority=50, enabled=True)
        
        # Coinbase - spot reference
        self.register(coinbase_adapter, priority=10, enabled=True)
    
    def register(
        self, 
        provider: MarketDataProvider, 
        priority: int = 50,
        enabled: bool = True
    ):
        """Регистрирует провайдера"""
        venue = provider.venue
        self._providers[venue] = provider
        self._priorities[venue] = priority
        self._enabled[venue] = enabled
    
    def get(self, venue: Venue) -> Optional[MarketDataProvider]:
        """Получает провайдера по venue"""
        if venue in self._providers and self._enabled.get(venue, False):
            return self._providers[venue]
        return None
    
    def get_all(self, enabled_only: bool = True) -> List[MarketDataProvider]:
        """Получает список всех провайдеров"""
        providers = []
        for venue, provider in self._providers.items():
            if enabled_only and not self._enabled.get(venue, False):
                continue
            providers.append(provider)
        return providers
    
    def get_by_priority(self, enabled_only: bool = True) -> List[MarketDataProvider]:
        """Получает провайдеров отсортированных по приоритету"""
        providers = self.get_all(enabled_only)
        return sorted(providers, key=lambda p: self._priorities.get(p.venue, 0), reverse=True)
    
    def get_best_provider(self, capability: str = None) -> Optional[MarketDataProvider]:
        """Получает лучшего доступного провайдера"""
        for provider in self.get_by_priority():
            if capability:
                caps = provider.capabilities()
                if not getattr(caps, capability, False):
                    continue
            return provider
        return None
    
    def get_providers_with_capability(self, capability: str) -> List[MarketDataProvider]:
        """Получает провайдеров с определенной capability"""
        result = []
        for provider in self.get_by_priority():
            caps = provider.capabilities()
            if getattr(caps, capability, False):
                result.append(provider)
        return result
    
    def set_enabled(self, venue: Venue, enabled: bool):
        """Включает/выключает провайдера"""
        self._enabled[venue] = enabled
    
    def set_priority(self, venue: Venue, priority: int):
        """Устанавливает приоритет провайдера"""
        self._priorities[venue] = priority
    
    def get_priority(self, venue: Venue) -> int:
        """Получает приоритет провайдера"""
        return self._priorities.get(venue, 0)
    
    def is_enabled(self, venue: Venue) -> bool:
        """Проверяет включен ли провайдер"""
        return self._enabled.get(venue, False)
    
    def list_venues(self) -> List[Dict]:
        """Список всех зарегистрированных venues"""
        result = []
        for venue in self._providers:
            provider = self._providers[venue]
            caps = provider.capabilities()
            result.append({
                "venue": venue.value,
                "priority": self._priorities.get(venue, 0),
                "enabled": self._enabled.get(venue, False),
                "capabilities": caps.model_dump()
            })
        return sorted(result, key=lambda x: x["priority"], reverse=True)
    
    async def health_check_all(self) -> Dict[str, Dict]:
        """Проверяет здоровье всех провайдеров"""
        results = {}
        for venue, provider in self._providers.items():
            try:
                health = await provider.health_check()
                results[venue.value] = health
            except Exception as e:
                results[venue.value] = {
                    "venue": venue.value,
                    "healthy": False,
                    "latency_ms": None,
                    "error": str(e)
                }
        return results


# Singleton instance
provider_registry = ProviderRegistry()
