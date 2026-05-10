from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import NamedTuple, Dict, List, Optional

logger = logging.getLogger(__name__)


class PromptEntry(NamedTuple):
    """Immutable cache entry with content and source metadata."""
    content: str
    source: Path


class PromptNotFoundError(FileNotFoundError):
    """Raised when a requested prompt file does not exist."""


class PromptLoader:
    """
    Thread-safe, production-grade loader for AI prompt files.

    Prompts are stored as .md or .txt files under app/ai/prompts/.
    Results are cached in memory after the first disk read.
    """

    _base_dir: Path = Path(__file__).parent / "prompts"
    _cache: Dict[str, PromptEntry] = {}
    _lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, name: str) -> str:
        """
        Returns the prompt string for *name*, reading from disk on first call.
        """
        with cls._lock:
            if name in cls._cache:
                return cls._cache[name].content

            return cls._load_from_disk(name)

    @classmethod
    def get_default_system(cls) -> str:
        """Convenience helper — loads 'default_system' prompt."""
        return cls.load("default_system")

    @classmethod
    def hot_reload(cls, name: str) -> str:
        """
        Forces a fresh disk read for *name* and updates the cache entry.
        """
        with cls._lock:
            entry = cls._read_file(name)          # raises if missing
            cls._cache[name] = entry
            logger.info(f"Prompt '{name}' hot-reloaded from {entry.source}")
            return entry.content

    @classmethod
    def load_all(cls) -> Dict[str, str]:
        """
        Eagerly loads every prompt file in _base_dir into the cache.
        """
        result: Dict[str, str] = {}
        with cls._lock:
            if not cls._base_dir.exists():
                logger.error(f"Prompts directory missing: {cls._base_dir}")
                return result
                
            for file_path in sorted(cls._base_dir.glob("*")):
                if file_path.suffix not in {".md", ".txt"}:
                    continue
                name = file_path.stem
                try:
                    content = cls._load_from_disk(name)
                    result[name] = content
                except PromptNotFoundError:
                    # Genuinely missing or disappeared
                    pass
                except Exception as exc:
                    # Unexpected error (permissions, disk failure, etc)
                    logger.error(f"Critical error loading prompt '{name}' from {file_path}: {exc}")

        logger.info(
            f"Prompt cache warmed: {len(result)} prompts loaded "
            f"({', '.join(result.keys()) or 'none'})"
        )
        return result

    @classmethod
    def clear_cache(cls) -> None:
        """Clears the entire in-memory cache. Intended for tests and admin resets."""
        with cls._lock:
            cls._cache.clear()
        logger.info("Prompt cache cleared.")

    @classmethod
    def cached_names(cls) -> List[str]:
        """Returns the names of all currently cached prompts (for observability)."""
        with cls._lock:
            return list(cls._cache.keys())

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @classmethod
    def _load_from_disk(cls, name: str) -> str:
        """Reads *name* from disk, stores in cache, and returns the content."""
        entry = cls._read_file(name)     # raises PromptNotFoundError if missing
        cls._cache[name] = entry
        logger.debug(f"Prompt '{name}' cached from {entry.source}")
        return entry.content

    @classmethod
    def _read_file(cls, name: str) -> PromptEntry:
        """
        Resolves the file path for *name* and reads it.
        """
        for ext in (".md", ".txt"):
            file_path = cls._base_dir / f"{name}{ext}"
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8").strip()
                    return PromptEntry(content=content, source=file_path)
                except OSError as exc:
                    logger.error(f"Failed to read prompt file '{file_path}': {exc}")
                    raise PromptNotFoundError(
                        f"Prompt '{name}' exists at {file_path} but could not be read."
                    ) from exc

        raise PromptNotFoundError(
            f"Prompt '{name}' not found in '{cls._base_dir}'. "
            f"Looked for: {name}.md, {name}.txt"
        )
