"""
Scraper Engine - Core Models
Full request blueprint for replay
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import json
import hashlib


@dataclass
class CapturedRequest:
    """
    Full request blueprint for exact replay.
    Captures everything needed to reproduce the request.
    """
    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    cookies: Dict[str, str] = field(default_factory=dict)
    
    # Metadata
    source: str = ""           # "dropstab" | "cryptorank"
    target: str = ""           # "unlocks" | "funding" | "investors"
    captured_at: str = ""
    from_page: str = ""        # Original page URL
    
    # Response hints
    response_status: int = 0
    response_type: str = ""    # "list" | "paginated" | "object"
    response_keys: List[str] = field(default_factory=list)
    sample_size: int = 0       # Number of items if list
    
    # Scoring
    success_count: int = 0
    fail_count: int = 0
    last_success: str = ""
    last_error: str = ""
    
    @property
    def key(self) -> str:
        """Unique key for this endpoint"""
        return f"{self.source}:{self.target}:{self.method}:{self.url[:100]}"
    
    @property
    def hash(self) -> str:
        """Content hash for deduplication"""
        content = f"{self.url}|{self.method}|{json.dumps(self.headers, sort_keys=True)}"
        return hashlib.sha1(content.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CapturedRequest":
        # Filter out extra fields that may be in registry but not in dataclass
        valid_fields = {f.name for f in __import__('dataclasses').fields(cls)}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)
    
    def to_requests_kwargs(self) -> Dict[str, Any]:
        """Convert to requests library kwargs"""
        kwargs = {
            "url": self.url,
            "method": self.method,
            "headers": self._clean_headers(),
            "timeout": 30
        }
        if self.body:
            try:
                kwargs["json"] = json.loads(self.body)
            except:
                kwargs["data"] = self.body
        if self.cookies:
            kwargs["cookies"] = self.cookies
        return kwargs
    
    def _clean_headers(self) -> Dict[str, str]:
        """Clean headers for replay"""
        skip = {"content-length", "host", ":authority", ":method", ":path", ":scheme"}
        return {k: v for k, v in self.headers.items() if k.lower() not in skip}


@dataclass
class Job:
    """Scraper job definition"""
    id: str
    source: str              # "dropstab" | "cryptorank"
    kind: str                # "discover" | "sync" | "parse"
    target: str              # "unlocks" | "funding" | "investors"
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        return cls(**d)


@dataclass
class RawRecord:
    """Raw scraped data record"""
    id: str
    source: str
    target: str
    endpoint_url: str
    captured_at: str
    proxy_used: Optional[str]
    payload: Any
    meta: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
