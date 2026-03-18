# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Global in-memory caches for expensive objects.

Provides singleton cache management for LoreManager instances
to avoid rebuilding Aho-Corasick automata on every request.
"""

from typing import Dict, Optional, TYPE_CHECKING
from threading import Lock

__all__ = ["CacheManager", "cache_manager", "invalidate_novel_language_caches"]

if TYPE_CHECKING:
    from app.core.lore_manager import LoreManager


class CacheManager:
    """Thread-safe singleton cache for LoreManager instances."""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._lore_cache: Dict[int, "LoreManager"] = {}
        return cls._instance

    def get_lore(self, novel_id: int) -> Optional["LoreManager"]:
        """Get cached LoreManager instance for a novel."""
        return self._lore_cache.get(novel_id)

    def set_lore(self, novel_id: int, lore: "LoreManager") -> None:
        """Cache a LoreManager instance."""
        self._lore_cache[novel_id] = lore

    def invalidate_novel(self, novel_id: int) -> None:
        """Clear all caches for a novel (call after lorebook/chapter updates)."""
        self._lore_cache.pop(novel_id, None)


cache_manager = CacheManager()


def invalidate_novel_language_caches(db, novel_id: int) -> None:
    """Invalidate all caches affected by a Novel.language change.

    Must be called whenever Novel.language is mutated. This ensures:
    - Lore automaton is rebuilt (keyword language may change)
    - Window index revision is invalidated (tokenizer depends on language)

    Caller must commit the surrounding transaction and schedule a rebuild if
    they want the index refreshed immediately.
    """
    cache_manager.invalidate_novel(novel_id)
    from app.models import Novel
    from app.core.indexing.lifecycle import mark_window_index_inputs_changed
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel is not None:
        mark_window_index_inputs_changed(novel)
