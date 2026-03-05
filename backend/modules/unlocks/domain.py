"""
Unlock Domain Types
Layer 2: Token Unlocks
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UnlockCategory(str, Enum):
    """Категории анлоков"""
    TEAM = "team"
    INVESTOR = "investor"
    ECOSYSTEM = "ecosystem"
    TREASURY = "treasury"
    FOUNDATION = "foundation"
    ADVISOR = "advisor"
    MARKETING = "marketing"
    LIQUIDITY = "liquidity"
    COMMUNITY = "community"
    OTHER = "other"


class Project(BaseModel):
    """Криптопроект"""
    id: str = Field(..., description="Unique project ID")
    name: str
    symbol: str
    slug: str
    website: Optional[str] = None
    coingecko_id: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    
    # Token info
    total_supply: Optional[float] = None
    circulating_supply: Optional[float] = None
    max_supply: Optional[float] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class TokenUnlock(BaseModel):
    """Событие анлока токенов"""
    id: str = Field(..., description="Unique unlock ID")
    project_id: str
    project_symbol: str
    project_name: str
    
    # Unlock details
    unlock_date: datetime
    unlock_amount: float  # Token amount
    unlock_percent: float  # % of total supply
    unlock_value_usd: Optional[float] = None  # USD value at current price
    
    # Category
    category: UnlockCategory = UnlockCategory.OTHER
    description: Optional[str] = None
    
    # Source
    source: str = "dropstab"  # dropstab, cryptorank, manual
    source_url: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class UnlockSummary(BaseModel):
    """Сводка по анлокам проекта"""
    project_id: str
    project_symbol: str
    total_unlocks: int
    next_unlock: Optional[TokenUnlock] = None
    total_unlock_value_30d: Optional[float] = None
    total_unlock_percent_30d: Optional[float] = None


class UpcomingUnlock(BaseModel):
    """Предстоящий анлок с дополнительной инфой"""
    unlock: TokenUnlock
    days_until: int
    price_impact_estimate: Optional[str] = None  # low/medium/high
