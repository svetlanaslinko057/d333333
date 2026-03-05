"""
Storage utilities: upsert with change detection + moderation queue
"""

import hashlib
import json
import logging
from typing import Optional, Dict, Any, Literal
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


def hash_payload(obj: Dict) -> str:
    """Create hash of payload for change detection"""
    # Remove fields that change on every update
    clean = {k: v for k, v in obj.items() if k not in ['raw', 'updated_at', 'payloadHash']}
    json_str = json.dumps(clean, sort_keys=True, default=str)
    return hashlib.sha1(json_str.encode()).hexdigest()


async def upsert_with_diff(
    collection,
    doc: Dict,
    key_field: str = 'key'
) -> Dict[str, Any]:
    """
    Upsert document and detect if it changed.
    Returns: {changed: bool, change_type: 'new'|'updated'|None}
    """
    now = datetime.now(timezone.utc)
    payload_hash = hash_payload(doc)
    
    key_value = doc.get(key_field)
    if not key_value:
        return {'changed': False, 'change_type': None, 'error': 'No key'}
    
    existing = await collection.find_one({key_field: key_value})
    
    if not existing:
        # New document
        doc['payloadHash'] = payload_hash
        doc['created_at'] = now
        doc['updated_at'] = now
        await collection.insert_one(doc)
        return {'changed': True, 'change_type': 'new'}
    
    if existing.get('payloadHash') != payload_hash:
        # Updated document
        doc['payloadHash'] = payload_hash
        doc['updated_at'] = now
        await collection.update_one(
            {key_field: key_value},
            {'$set': doc}
        )
        return {'changed': True, 'change_type': 'updated'}
    
    # No change
    return {'changed': False, 'change_type': None}


async def push_to_moderation(
    db: AsyncIOMotorDatabase,
    source: str,
    entity: str,
    key: str,
    payload: Dict,
    change_type: Literal['new', 'updated'],
    meta: Optional[Dict] = None
):
    """
    Add item to moderation queue for admin review.
    """
    item = {
        'source': source,
        'entity': entity,
        'key': key,
        'payload': payload,
        'change_type': change_type,
        'status': 'pending',  # pending, approved, rejected
        'created_at': datetime.now(timezone.utc),
        'meta': meta or {}
    }
    
    await db.moderation_queue.insert_one(item)
    logger.debug(f"[Moderation] {change_type} {entity}: {key}")
