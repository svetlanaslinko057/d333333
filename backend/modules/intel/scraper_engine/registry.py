"""
Endpoint Registry with Full Request Blueprint
Stores discovered endpoints with complete replay information
"""

import json
import os
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone

from .models import CapturedRequest

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path("/app/data/registry/endpoints.json")


class EndpointRegistry:
    """
    Registry for discovered API endpoints.
    
    Features:
    - Full request blueprint storage (method, headers, body, cookies)
    - Scoring system (success/fail tracking)
    - Automatic fallback selection
    - Multiple candidates per target
    """
    
    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        if not self.path.exists():
            self._init_db()
    
    def _init_db(self):
        """Initialize empty database"""
        db = {
            "version": 1,
            "updatedAt": time.time(),
            "endpoints": []
        }
        self._save(db)
    
    def _load(self) -> Dict[str, Any]:
        """Load database"""
        try:
            return json.load(open(self.path, "r", encoding="utf-8"))
        except:
            self._init_db()
            return json.load(open(self.path, "r", encoding="utf-8"))
    
    def _save(self, db: Dict[str, Any]):
        """Save database"""
        db["updatedAt"] = time.time()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    
    def upsert(self, req: CapturedRequest) -> bool:
        """
        Add or update endpoint in registry.
        Returns True if new, False if updated.
        """
        db = self._load()
        endpoints = db["endpoints"]
        
        # Find existing
        existing_idx = None
        for i, e in enumerate(endpoints):
            if e.get("hash") == req.hash:
                existing_idx = i
                break
        
        data = req.to_dict()
        data["updatedAt"] = time.time()
        
        if existing_idx is not None:
            # Update existing
            old = endpoints[existing_idx]
            data["success_count"] = old.get("success_count", 0) + req.success_count
            data["fail_count"] = old.get("fail_count", 0) + req.fail_count
            endpoints[existing_idx] = data
            is_new = False
        else:
            # Add new
            endpoints.append(data)
            is_new = True
        
        self._save(db)
        logger.info(f"[Registry] {'Added' if is_new else 'Updated'}: {req.source}/{req.target} -> {req.url[:60]}")
        return is_new
    
    def get_best(self, source: str, target: str, limit: int = 5) -> List[CapturedRequest]:
        """
        Get best endpoints for source/target.
        Sorted by: success_rate, recency, sample_size
        """
        db = self._load()
        
        candidates = [
            e for e in db["endpoints"]
            if e.get("source") == source and e.get("target") == target
        ]
        
        # Score endpoints
        def score(e):
            success = e.get("success_count", 0)
            fail = e.get("fail_count", 0)
            total = success + fail
            rate = success / total if total > 0 else 0.5
            recency = e.get("updatedAt", 0)
            size = e.get("sample_size", 0)
            return (rate, recency, size)
        
        candidates.sort(key=score, reverse=True)
        
        return [CapturedRequest.from_dict(e) for e in candidates[:limit]]
    
    def get_all(self, source: str = None, target: str = None) -> List[CapturedRequest]:
        """Get all endpoints, optionally filtered"""
        db = self._load()
        
        endpoints = db["endpoints"]
        
        if source:
            endpoints = [e for e in endpoints if e.get("source") == source]
        if target:
            endpoints = [e for e in endpoints if e.get("target") == target]
        
        return [CapturedRequest.from_dict(e) for e in endpoints]
    
    def report_success(self, req: CapturedRequest):
        """Report successful request"""
        db = self._load()
        
        for e in db["endpoints"]:
            if e.get("hash") == req.hash:
                e["success_count"] = e.get("success_count", 0) + 1
                e["last_success"] = datetime.now(timezone.utc).isoformat()
                e["last_error"] = ""
                break
        
        self._save(db)
    
    def report_fail(self, req: CapturedRequest, error: str):
        """Report failed request"""
        db = self._load()
        
        for e in db["endpoints"]:
            if e.get("hash") == req.hash:
                e["fail_count"] = e.get("fail_count", 0) + 1
                e["last_error"] = error
                break
        
        self._save(db)
    
    def delete(self, hash: str) -> bool:
        """Delete endpoint by hash"""
        db = self._load()
        original_len = len(db["endpoints"])
        db["endpoints"] = [e for e in db["endpoints"] if e.get("hash") != hash]
        self._save(db)
        return len(db["endpoints"]) < original_len
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        db = self._load()
        endpoints = db["endpoints"]
        
        by_source = {}
        for e in endpoints:
            src = e.get("source", "unknown")
            tgt = e.get("target", "unknown")
            key = f"{src}/{tgt}"
            by_source[key] = by_source.get(key, 0) + 1
        
        return {
            "total": len(endpoints),
            "by_source_target": by_source,
            "updated_at": db.get("updatedAt")
        }


# Singleton
endpoint_registry = EndpointRegistry()
