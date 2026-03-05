from typing import Optional
"""
Activity/News parser
"""

from typing import Dict, List, Any
from datetime import datetime


def parse_timestamp(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value < 1e12 else int(value / 1000)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return int(dt.timestamp())
        except:
            return None
    return None


def parse_activity(data: List[Dict]) -> List[Dict]:
    """
    Parse activity/news feed from Dropstab.
    """
    results = []
    
    for a in data:
        title = a.get('title') or a.get('headline') or a.get('name')
        if not title:
            continue
        
        # Create unique key from title hash or id
        item_id = a.get('id') or a.get('slug') or str(hash(title))[:12]
        key = f"dropstab:activity:{item_id}"
        
        activity_type = (a.get('type') or a.get('category') or 'news').lower()
        
        # Extract related projects
        projects = []
        if a.get('project'):
            projects.append(a.get('project'))
        if a.get('symbol'):
            projects.append(a.get('symbol'))
        if a.get('projects') and isinstance(a.get('projects'), list):
            projects.extend(a.get('projects'))
        
        doc = {
            'key': key,
            'source': 'dropstab',
            
            'title': title,
            'type': activity_type,
            
            'date': parse_timestamp(a.get('date') or a.get('publishedAt') or a.get('timestamp')),
            
            'url': a.get('url') or a.get('link'),
            'image_url': a.get('image') or a.get('imageUrl') or a.get('thumbnail'),
            
            'content': a.get('content') or a.get('description') or a.get('summary'),
            
            'projects': list(set(projects)),  # dedupe
            
            'importance': a.get('importance') or a.get('priority') or 'normal',
            
            'raw': a
        }
        
        results.append(doc)
    
    return results
