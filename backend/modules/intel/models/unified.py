"""
Unified Intel Models - Common data structures for all sources

These models define the canonical schema that all source parsers
must convert their data into. The frontend and API work only with
these unified models, never with raw source data.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import hashlib


class UnlockType(str, Enum):
    VESTING = "vesting"
    TGE = "tge"
    CLIFF = "cliff"
    LINEAR = "linear"
    OTHER = "other"


class FundingStage(str, Enum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    PRIVATE = "private"
    STRATEGIC = "strategic"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C = "series_c"
    PUBLIC = "public"
    OTHER = "other"


class SaleType(str, Enum):
    ICO = "ico"
    IEO = "ieo"
    IDO = "ido"
    IGO = "igo"
    PRIVATE_SALE = "private_sale"
    PUBLIC_SALE = "public_sale"
    OTHER = "other"


class InvestorTier(str, Enum):
    TIER_1 = "tier_1"  # Top VCs (a16z, Paradigm, etc)
    TIER_2 = "tier_2"  # Major funds
    TIER_3 = "tier_3"  # Regular funds
    ANGEL = "angel"
    OTHER = "other"


# ═══════════════════════════════════════════════════════════════
# UNIFIED MODELS
# ═══════════════════════════════════════════════════════════════

@dataclass
class IntelUnlock:
    """
    Token unlock event - unified schema.
    
    Sources: Dropstab, CryptoRank
    """
    # Identifiers
    id: str = ""                    # Generated unique ID
    source: str = ""                # "dropstab" | "cryptorank"
    source_id: str = ""             # Original ID from source
    
    # Project info
    project: str = ""               # Project name
    symbol: str = ""                # Token symbol (uppercase)
    project_key: str = ""           # Slug/key for linking
    
    # Unlock details
    unlock_date: int = 0            # Unix timestamp
    unlock_type: str = "vesting"    # UnlockType value
    
    # Amounts
    amount_tokens: Optional[float] = None
    amount_usd: Optional[float] = None
    percent_supply: Optional[float] = None
    
    # Metadata
    is_hidden: bool = False
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def _generate_id(self) -> str:
        """Generate deterministic ID for deduplication"""
        key = f"{self.symbol}:{self.unlock_date}:{self.unlock_type}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop('raw_data', None)  # Don't include raw in output
        return d
    
    def to_mongo(self) -> Dict[str, Any]:
        """Convert to MongoDB document"""
        return {
            **self.to_dict(),
            "raw_data": self.raw_data
        }


@dataclass
class IntelFunding:
    """
    Funding round - unified schema.
    
    Sources: Dropstab, CryptoRank
    """
    # Identifiers
    id: str = ""
    source: str = ""
    source_id: str = ""
    
    # Project info
    project: str = ""
    symbol: str = ""
    project_key: str = ""
    
    # Round details
    round_type: str = "other"       # FundingStage value
    round_date: int = 0             # Unix timestamp
    
    # Amounts
    raised_usd: Optional[float] = None
    valuation_usd: Optional[float] = None
    
    # Investors
    investors: List[str] = field(default_factory=list)       # Names
    lead_investors: List[str] = field(default_factory=list)  # Lead names
    investor_count: int = 0
    
    # Metadata
    raw_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def _generate_id(self) -> str:
        key = f"{self.project_key}:{self.round_type}:{self.round_date}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop('raw_data', None)
        return d
    
    def to_mongo(self) -> Dict[str, Any]:
        return {**self.to_dict(), "raw_data": self.raw_data}


@dataclass
class IntelInvestor:
    """
    Investor/VC/Fund - unified schema.
    
    Sources: Dropstab, CryptoRank
    """
    # Identifiers
    id: str = ""
    source: str = ""
    source_id: str = ""
    
    # Info
    name: str = ""
    slug: str = ""
    tier: str = "other"             # InvestorTier value
    category: str = ""              # "venture", "hedge", "angel", etc
    
    # Stats
    investments_count: int = 0
    portfolio: List[str] = field(default_factory=list)  # Project keys
    
    # Social/Links
    website: str = ""
    twitter: str = ""
    logo_url: str = ""
    
    # Metadata
    raw_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def _generate_id(self) -> str:
        key = f"{self.source}:{self.slug}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop('raw_data', None)
        return d
    
    def to_mongo(self) -> Dict[str, Any]:
        return {**self.to_dict(), "raw_data": self.raw_data}


@dataclass
class IntelSale:
    """
    Token sale (ICO/IEO/IDO) - unified schema.
    
    Sources: Dropstab, CryptoRank
    """
    # Identifiers
    id: str = ""
    source: str = ""
    source_id: str = ""
    
    # Project info
    project: str = ""
    symbol: str = ""
    project_key: str = ""
    
    # Sale details
    sale_type: str = "other"        # SaleType value
    platform: str = ""              # Launchpad name
    
    # Dates
    start_date: Optional[int] = None
    end_date: Optional[int] = None
    
    # Amounts
    price_usd: Optional[float] = None
    raise_usd: Optional[float] = None
    raise_target_usd: Optional[float] = None
    
    # ROI
    current_price_usd: Optional[float] = None
    roi_usd: Optional[float] = None
    ath_roi_usd: Optional[float] = None
    
    # Metadata
    raw_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def _generate_id(self) -> str:
        key = f"{self.project_key}:{self.sale_type}:{self.platform}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop('raw_data', None)
        return d
    
    def to_mongo(self) -> Dict[str, Any]:
        return {**self.to_dict(), "raw_data": self.raw_data}


# ═══════════════════════════════════════════════════════════════
# EVENT INDEX MODEL
# ═══════════════════════════════════════════════════════════════

@dataclass
class IntelEvent:
    """
    Unified event for fast indexing.
    
    All unlocks, funding, sales are also stored here for quick queries.
    """
    # Identifiers
    id: str = ""
    event_type: str = ""            # "unlock" | "funding" | "sale"
    source: str = ""
    source_id: str = ""
    
    # Project
    symbol: str = ""
    project: str = ""
    project_key: str = ""
    
    # Event
    event_date: int = 0             # Unix timestamp
    
    # Amounts (normalized)
    amount_usd: Optional[float] = None
    
    # Sources that confirm this event
    sources: List[str] = field(default_factory=list)
    confidence: float = 0.5         # 0.0 - 1.0
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def _generate_id(self) -> str:
        key = f"{self.event_type}:{self.symbol}:{self.event_date}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_mongo(self) -> Dict[str, Any]:
        return self.to_dict()
