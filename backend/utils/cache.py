"""
CVM Analyzer - Cache Manager
=========================

LRU cache for PDFs and CSVs with 5GB limit.
Pins recent FREs (last 3 years + most recent) to prevent deletion.
"""

import os
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
import logging


@dataclass
class CacheEntry:
    """Metadata for a cached file."""
    key: str
    path: str
    size_bytes: int
    created_at: str
    last_accessed: str
    is_pinned: bool = False
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class CacheManager:
    """
    LRU cache manager with size limit and pinning support.
    
    Features:
    - 5GB max size (configurable)
    - LRU eviction for unpinned files
    - Pinned files are never evicted
    - Atomic file operations
    """
    
    def __init__(
        self,
        cache_dir: Path,
        max_size_bytes: int = 5 * 1024 * 1024 * 1024,  # 5GB
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory for cached files
            max_size_bytes: Maximum cache size in bytes
            logger: Logger instance
        """
        self.cache_dir = Path(cache_dir)
        self.max_size_bytes = max_size_bytes
        self.logger = logger or logging.getLogger(__name__)
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache index file
        self.index_path = self.cache_dir / ".cache_index.json"
        self.index: Dict[str, CacheEntry] = {}
        
        # Load existing index
        self._load_index()
    
    def _load_index(self):
        """Load cache index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.index = {
                        k: CacheEntry(**v) for k, v in data.items()
                    }
                self.logger.debug(f"Loaded cache index with {len(self.index)} entries")
            except Exception as e:
                self.logger.warning(f"Failed to load cache index: {e}")
                self.index = {}
                self._rebuild_index()
    
    def _save_index(self):
        """Save cache index to disk."""
        try:
            data = {k: asdict(v) for k, v in self.index.items()}
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save cache index: {e}")
    
    def _rebuild_index(self):
        """Rebuild index from existing files."""
        self.logger.info("Rebuilding cache index...")
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                key = str(file_path.relative_to(self.cache_dir))
                stat = file_path.stat()
                self.index[key] = CacheEntry(
                    key=key,
                    path=str(file_path),
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    last_accessed=datetime.fromtimestamp(stat.st_atime).isoformat(),
                    is_pinned=False
                )
        self._save_index()
    
    def _generate_key(self, identifier: str, extension: str = "") -> str:
        """Generate a cache key from identifier."""
        hash_val = hashlib.sha256(identifier.encode()).hexdigest()[:16]
        return f"{hash_val}{extension}"
    
    def _get_total_size(self) -> int:
        """Calculate total cache size in bytes."""
        return sum(entry.size_bytes for entry in self.index.values())
    
    def _evict_if_needed(self, required_bytes: int):
        """Evict unpinned files using LRU until enough space is available."""
        current_size = self._get_total_size()
        target_size = self.max_size_bytes - required_bytes
        
        if current_size <= target_size:
            return  # No eviction needed
        
        # Sort unpinned entries by last_accessed (oldest first)
        unpinned = [
            (k, v) for k, v in self.index.items() 
            if not v.is_pinned
        ]
        unpinned.sort(key=lambda x: x[1].last_accessed)
        
        for key, entry in unpinned:
            if current_size <= target_size:
                break
            
            # Delete file
            try:
                file_path = Path(entry.path)
                if file_path.exists():
                    file_path.unlink()
                    self.logger.info(f"Evicted from cache: {key} ({entry.size_bytes} bytes)")
                
                current_size -= entry.size_bytes
                del self.index[key]
            except Exception as e:
                self.logger.error(f"Failed to evict {key}: {e}")
        
        self._save_index()
    
    def get(self, key: str) -> Optional[Path]:
        """
        Get a cached file by key.
        
        Args:
            key: Cache key
            
        Returns:
            Path to cached file or None if not found
        """
        if key in self.index:
            entry = self.index[key]
            file_path = Path(entry.path)
            
            if file_path.exists():
                # Update last accessed time
                entry.last_accessed = datetime.utcnow().isoformat()
                self._save_index()
                return file_path
            else:
                # File was deleted externally
                del self.index[key]
                self._save_index()
        
        return None
    
    def put(
        self,
        key: str,
        data: bytes,
        pinned: bool = False,
        metadata: Optional[Dict] = None
    ) -> Path:
        """
        Store data in cache.
        
        Args:
            key: Cache key (can include subdirectory, e.g., "pdfs/doc.pdf")
            data: File content as bytes
            pinned: If True, file won't be evicted
            metadata: Additional metadata to store
            
        Returns:
            Path to cached file
        """
        file_path = self.cache_dir / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Evict if needed
        self._evict_if_needed(len(data))
        
        # Write file atomically
        temp_path = file_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'wb') as f:
                f.write(data)
            temp_path.rename(file_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise
        
        # Update index
        now = datetime.utcnow().isoformat()
        self.index[key] = CacheEntry(
            key=key,
            path=str(file_path),
            size_bytes=len(data),
            created_at=now,
            last_accessed=now,
            is_pinned=pinned,
            metadata=metadata or {}
        )
        self._save_index()
        
        self.logger.debug(f"Cached: {key} ({len(data)} bytes, pinned={pinned})")
        return file_path
    
    def pin(self, key: str, pinned: bool = True):
        """Set or unset pinned status for a cache entry."""
        if key in self.index:
            self.index[key].is_pinned = pinned
            self._save_index()
            self.logger.debug(f"{'Pinned' if pinned else 'Unpinned'}: {key}")
    
    def delete(self, key: str) -> bool:
        """Delete a cached file."""
        if key in self.index:
            entry = self.index[key]
            try:
                file_path = Path(entry.path)
                if file_path.exists():
                    file_path.unlink()
                del self.index[key]
                self._save_index()
                self.logger.debug(f"Deleted from cache: {key}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to delete {key}: {e}")
        return False
    
    def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        if key in self.index:
            return Path(self.index[key].path).exists()
        return False
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        total_size = self._get_total_size()
        pinned_size = sum(
            e.size_bytes for e in self.index.values() if e.is_pinned
        )
        return {
            "total_entries": len(self.index),
            "total_size_bytes": total_size,
            "total_size_gb": round(total_size / (1024**3), 2),
            "max_size_gb": round(self.max_size_bytes / (1024**3), 2),
            "usage_percent": round(total_size / self.max_size_bytes * 100, 1),
            "pinned_entries": sum(1 for e in self.index.values() if e.is_pinned),
            "pinned_size_bytes": pinned_size
        }
    
    def clear_unpinned(self):
        """Clear all unpinned entries."""
        for key in list(self.index.keys()):
            if not self.index[key].is_pinned:
                self.delete(key)
        self.logger.info("Cleared all unpinned cache entries")


# =============================================================================
# Global Cache Instance
# =============================================================================

_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get or create the cache manager singleton."""
    global _cache_manager
    if _cache_manager is None:
        from config import get_settings
        from utils.logger import get_logger
        
        settings = get_settings()
        _cache_manager = CacheManager(
            cache_dir=settings.cache_dir,
            max_size_bytes=int(settings.cache_max_size_gb * 1024**3),
            logger=get_logger()
        )
    return _cache_manager
