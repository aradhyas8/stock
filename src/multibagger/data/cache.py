"""HTTP response caching with SQLite backend"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from multibagger.common.utils import check_ttl_fresh, generate_cache_key
from multibagger.database.models import HttpCache as HttpCacheModel
from multibagger.database.schema import get_engine

logger = logging.getLogger(__name__)


class CacheStats:
    """Cache statistics"""

    def __init__(
        self,
        total_entries: int = 0,
        expired_entries: int = 0,
        size_bytes: int = 0,
        oldest_entry: datetime | None = None,
        newest_entry: datetime | None = None,
        hit_rate: float = 0.0,
        top_keys: list[str] | None = None,
    ):
        self.total_entries = total_entries
        self.expired_entries = expired_entries
        self.size_bytes = size_bytes
        self.oldest_entry = oldest_entry
        self.newest_entry = newest_entry
        self.hit_rate = hit_rate
        self.top_keys = top_keys or []


class HttpCache:
    """
    HTTP response cache with SQLite backend.

    Provides three-tier caching:
    1. In-memory hot cache (dict)
    2. SQLite persistent cache
    3. Network fetch (with automatic caching)
    """

    def __init__(self, db_path: str | None = None):
        self.engine = get_engine(db_path)
        self._hot_cache: dict[str, tuple[Any, datetime]] = {}
        self._stats = {"hits": 0, "misses": 0}

    def get(
        self,
        url: str,
        ttl_days: int = 1,
        force_refresh: bool = False,
    ) -> tuple[Any, bool]:
        """
        Get cached response or None.

        Returns:
            Tuple of (data, is_from_cache)
        """
        cache_key = generate_cache_key(url)

        if force_refresh:
            self._stats["misses"] += 1
            return None, False

        # Check hot cache first
        if cache_key in self._hot_cache:
            data, created_at = self._hot_cache[cache_key]
            if check_ttl_fresh(created_at, ttl_days):
                self._stats["hits"] += 1
                logger.debug(f"Hot cache hit: {url[:80]}")
                return data, True

        # Check SQLite cache
        with Session(self.engine) as session:
            result = session.execute(
                select(HttpCacheModel).where(HttpCacheModel.cache_key == cache_key)
            ).scalar_one_or_none()

            if result:
                if check_ttl_fresh(result.created_at, ttl_days):
                    # Cache hit
                    data = json.loads(result.response_data)

                    # Update hot cache
                    self._hot_cache[cache_key] = (data, result.created_at)

                    self._stats["hits"] += 1
                    logger.debug(f"SQLite cache hit: {url[:80]}")
                    return data, True

        # Cache miss
        self._stats["misses"] += 1
        return None, False

    def put(
        self,
        url: str,
        data: Any,
        ttl_days: int = 1,
        status_code: int = 200,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        """Store data in cache"""
        cache_key = generate_cache_key(url)
        now = datetime.utcnow()
        expires_at = now + timedelta(days=ttl_days)

        # Update hot cache
        self._hot_cache[cache_key] = (data, now)

        # Update SQLite cache
        with Session(self.engine) as session:
            # Check if exists
            existing = session.execute(
                select(HttpCacheModel).where(HttpCacheModel.cache_key == cache_key)
            ).scalar_one_or_none()

            if existing:
                # Update
                existing.response_data = json.dumps(data)
                existing.status_code = status_code
                existing.etag = etag
                existing.last_modified = last_modified
                existing.ttl_days = ttl_days
                existing.expires_at = expires_at
                existing.created_at = now
            else:
                # Insert
                cache_entry = HttpCacheModel(
                    cache_key=cache_key,
                    url=url,
                    response_data=json.dumps(data),
                    status_code=status_code,
                    etag=etag,
                    last_modified=last_modified,
                    ttl_days=ttl_days,
                    expires_at=expires_at,
                )
                session.add(cache_entry)

            session.commit()
            logger.debug(f"Cached: {url[:80]}")

    def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        with Session(self.engine) as session:
            # Count entries
            total = session.execute(
                select(text("COUNT(*)")).select_from(HttpCacheModel)
            ).scalar()

            # Count expired
            expired = session.execute(
                select(text("COUNT(*)"))
                .select_from(HttpCacheModel)
                .where(HttpCacheModel.expires_at < datetime.utcnow())
            ).scalar()

            # Get date range
            oldest = session.execute(
                select(HttpCacheModel.created_at).order_by(HttpCacheModel.created_at)
            ).scalar()

            newest = session.execute(
                select(HttpCacheModel.created_at).order_by(
                    HttpCacheModel.created_at.desc()
                )
            ).scalar()

            # Calculate hit rate
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0
            )

            return CacheStats(
                total_entries=total or 0,
                expired_entries=expired or 0,
                size_bytes=0,  # Would need to calculate
                oldest_entry=oldest,
                newest_entry=newest,
                hit_rate=hit_rate,
                top_keys=[],
            )

    def prune(self, older_than_days: int = 30) -> int:
        """
        Remove old cache entries.

        Returns:
            Number of entries removed
        """
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)

        with Session(self.engine) as session:
            result = session.execute(
                text("DELETE FROM http_cache WHERE created_at < :cutoff"),
                {"cutoff": cutoff},
            )
            count = result.rowcount
            session.commit()

            logger.info(f"Pruned {count} cache entries older than {older_than_days} days")
            return count

    def clear(self) -> None:
        """Clear all cache"""
        self._hot_cache.clear()

        with Session(self.engine) as session:
            session.execute(text("DELETE FROM http_cache"))
            session.commit()

        logger.info("Cache cleared")
