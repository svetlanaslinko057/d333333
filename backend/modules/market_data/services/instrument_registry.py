"""
Instrument Registry Service
Управление инструментами и маппингом символов
"""

from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
import asyncio

from ..domain.types import (
    Venue, MarketType, Instrument, SymbolMapping, Asset
)
from ..providers.registry import provider_registry

class InstrumentRegistry:
    """
    Реестр торговых инструментов.
    Хранит все инструменты со всех бирж и маппинг к базовым активам.
    """
    
    def __init__(self):
        # instrument_id -> Instrument
        self._instruments: Dict[str, Instrument] = {}
        
        # asset_id -> Asset
        self._assets: Dict[str, Asset] = {}
        
        # asset_id -> List[instrument_id]
        self._asset_instruments: Dict[str, List[str]] = {}
        
        # symbol_mappings
        self._mappings: List[SymbolMapping] = []
        
        # Кеш
        self._last_sync: Optional[datetime] = None
        self._sync_lock = asyncio.Lock()
    
    async def sync_all(self, force: bool = False):
        """Синхронизирует инструменты со всех бирж"""
        async with self._sync_lock:
            # Проверяем нужна ли синхронизация
            if not force and self._last_sync:
                elapsed = (datetime.now(timezone.utc) - self._last_sync).total_seconds()
                if elapsed < 300:  # 5 минут кеш
                    return
            
            providers = provider_registry.get_all()
            
            for provider in providers:
                try:
                    # Синхронизируем perp инструменты
                    if provider.capabilities().has_perp:
                        instruments = await provider.list_instruments("perp")
                        for inst in instruments:
                            self._instruments[inst.instrument_id] = inst
                            self._create_asset_mapping(inst)
                    
                    # Синхронизируем spot инструменты
                    if provider.capabilities().has_spot:
                        instruments = await provider.list_instruments("spot")
                        for inst in instruments:
                            self._instruments[inst.instrument_id] = inst
                            self._create_asset_mapping(inst)
                
                except Exception as e:
                    print(f"[InstrumentRegistry] Failed to sync {provider.venue}: {e}")
            
            self._last_sync = datetime.now(timezone.utc)
            print(f"[InstrumentRegistry] Synced {len(self._instruments)} instruments, {len(self._assets)} assets")
    
    def _create_asset_mapping(self, instrument: Instrument):
        """Создает маппинг инструмента к базовому активу"""
        # Определяем asset_id из base символа
        asset_id = instrument.base.lower()
        
        # Создаем Asset если не существует
        if asset_id not in self._assets:
            self._assets[asset_id] = Asset(
                asset_id=asset_id,
                symbol=instrument.base,
                name=instrument.base,  # Можно обогатить из Asset Intel
                type="cryptocurrency"
            )
        
        # Добавляем инструмент к активу
        if asset_id not in self._asset_instruments:
            self._asset_instruments[asset_id] = []
        
        if instrument.instrument_id not in self._asset_instruments[asset_id]:
            self._asset_instruments[asset_id].append(instrument.instrument_id)
        
        # Создаем mapping
        priority = provider_registry.get_priority(instrument.venue)
        mapping = SymbolMapping(
            asset_id=asset_id,
            instrument_id=instrument.instrument_id,
            venue=instrument.venue,
            market_type=instrument.market_type,
            native_symbol=instrument.native_symbol,
            priority=priority
        )
        
        # Проверяем дубликаты
        existing = next(
            (m for m in self._mappings if m.instrument_id == instrument.instrument_id),
            None
        )
        if not existing:
            self._mappings.append(mapping)
    
    def get_instrument(self, instrument_id: str) -> Optional[Instrument]:
        """Получает инструмент по ID"""
        return self._instruments.get(instrument_id)
    
    def get_instrument_by_symbol(
        self, 
        venue: Venue, 
        native_symbol: str,
        market_type: str = "perp"
    ) -> Optional[Instrument]:
        """Получает инструмент по venue + symbol"""
        instrument_id = Instrument.make_id(venue.value, market_type, native_symbol)
        return self._instruments.get(instrument_id)
    
    def get_asset(self, asset_id: str) -> Optional[Asset]:
        """Получает базовый актив"""
        return self._assets.get(asset_id)
    
    def get_asset_instruments(self, asset_id: str) -> List[Instrument]:
        """Получает все инструменты для актива"""
        instrument_ids = self._asset_instruments.get(asset_id, [])
        return [self._instruments[iid] for iid in instrument_ids if iid in self._instruments]
    
    def get_primary_instrument(self, asset_id: str, market_type: MarketType = None) -> Optional[Instrument]:
        """Получает primary инструмент для актива (по приоритету)"""
        instruments = self.get_asset_instruments(asset_id)
        
        if market_type:
            instruments = [i for i in instruments if i.market_type == market_type]
        
        if not instruments:
            return None
        
        # Сортируем по приоритету venue
        instruments.sort(
            key=lambda i: provider_registry.get_priority(i.venue),
            reverse=True
        )
        
        return instruments[0]
    
    def list_instruments(
        self, 
        venue: Venue = None, 
        market_type: MarketType = None
    ) -> List[Instrument]:
        """Список инструментов с фильтрацией"""
        result = list(self._instruments.values())
        
        if venue:
            result = [i for i in result if i.venue == venue]
        
        if market_type:
            result = [i for i in result if i.market_type == market_type]
        
        return result
    
    def list_assets(self) -> List[Asset]:
        """Список всех базовых активов"""
        return list(self._assets.values())
    
    def search_assets(self, query: str, limit: int = 20) -> List[Asset]:
        """Поиск активов по запросу"""
        query = query.lower()
        results = []
        
        for asset in self._assets.values():
            if (query in asset.asset_id or 
                query in asset.symbol.lower() or 
                query in asset.name.lower()):
                results.append(asset)
                if len(results) >= limit:
                    break
        
        return results
    
    def get_venues_for_asset(self, asset_id: str) -> List[Venue]:
        """Получает список бирж где торгуется актив"""
        instruments = self.get_asset_instruments(asset_id)
        venues = set(i.venue for i in instruments)
        return list(venues)
    
    def get_mappings_for_asset(self, asset_id: str) -> List[SymbolMapping]:
        """Получает все маппинги для актива"""
        return [m for m in self._mappings if m.asset_id == asset_id]
    
    def stats(self) -> Dict:
        """Статистика реестра"""
        return {
            "total_instruments": len(self._instruments),
            "total_assets": len(self._assets),
            "total_mappings": len(self._mappings),
            "by_venue": {
                v.value: len([i for i in self._instruments.values() if i.venue == v])
                for v in Venue
            },
            "by_market_type": {
                mt.value: len([i for i in self._instruments.values() if i.market_type == mt])
                for mt in MarketType
            },
            "last_sync": self._last_sync.isoformat() if self._last_sync else None
        }


# Singleton instance
instrument_registry = InstrumentRegistry()
