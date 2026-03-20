# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("background_agent.store")


# Search result container.
# Semantic search result record.
@dataclass
class SearchResult:
    chunk: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


# In-memory vector storage backend.
class InMemoryVSBackend:
    # Initialize the in-memory store.
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    # Store chunks and embeddings for one task.
    async def add(
        self,
        task_id: str,
        chunks: List[str],
        embeddings,
        metadata: Optional[List[Dict[str, Any]]] = None,
        ttl_sec: float = 600.0,
    ) -> None:
        """Save task data in memory with a TTL."""

        async with self._lock:
            self._store[task_id] = {
                "chunks": chunks,
                "embeddings": embeddings,
                "metadata": metadata or [{} for _ in chunks],
                "expires_at": time.time() + ttl_sec,
            }

        logger.info(
            f"[InMemory] task={task_id}: stored {len(chunks)} chunks, TTL={ttl_sec}s"
        )

    # Search stored embeddings with cosine similarity.
    async def search(
        self,
        task_id: str,
        query_embedding,
        top_k: int = 5,
        min_score: float = 0.45,
    ) -> List[SearchResult]:
        """Return the highest-scoring chunks for a task."""

        import numpy as np

        async with self._lock:
            entry = self._store.get(task_id)
            if not entry:
                return []

            if time.time() > entry["expires_at"]:
                del self._store[task_id]
                return []

            chunks = entry["chunks"]
            embeddings = entry["embeddings"]
            metadata = entry["metadata"]

        # Normalize vectors before cosine scoring.
        query = query_embedding / (np.linalg.norm(query_embedding) + 1e-9)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9
        normalized_embeddings = embeddings / norms
        scores = normalized_embeddings @ query

        # Keep only the stronger half of the distribution.
        mean_score = float(np.mean(scores))
        std_score = float(np.std(scores))
        adaptive_threshold = max(min_score, mean_score + 1.0 * std_score)

        top_indices = np.argsort(scores)[::-1][: top_k * 3]
        results: List[SearchResult] = []

        for index in top_indices:
            score = float(scores[index])
            if score < adaptive_threshold:
                break

            results.append(
                SearchResult(
                    chunk=chunks[index],
                    score=round(score, 4),
                    metadata=metadata[index],
                )
            )

            if len(results) >= top_k:
                break

        return results

    # Remove one task from memory.
    async def purge(self, task_id: str) -> None:
        """Delete one task from the in-memory store."""

        async with self._lock:
            if task_id in self._store:
                del self._store[task_id]
                logger.info(f"[InMemory] task={task_id}: purged")

    # Remove all expired tasks.
    async def purge_expired(self) -> int:
        """Delete expired tasks and return the number of removed entries."""

        now = time.time()

        async with self._lock:
            expired_task_ids = [
                task_id
                for task_id, entry in self._store.items()
                if now > entry["expires_at"]
            ]

            for task_id in expired_task_ids:
                del self._store[task_id]

        if expired_task_ids:
            logger.info(
                f"[InMemory] purged {len(expired_task_ids)} expired tasks: "
                f"{expired_task_ids}"
            )

        return len(expired_task_ids)

    # Expose the number of tracked tasks.
    @property
    def task_count(self) -> int:
        return len(self._store)


# Redis-backed vector storage backend.
class RedisVSBackend:
    # Configure the Redis backend.
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self._client = None
        self._available: Optional[bool] = None

    # Check whether Redis and redisvl are available.
    def is_available(self) -> bool:
        """Return True when the Redis backend can be used."""

        if self._available is not None:
            return self._available

        try:
            import redis as redis_client
            import redisvl  # noqa: F401

            client = redis_client.from_url(self.redis_url, socket_connect_timeout=1)
            client.ping()
            self._client = client
            self._available = True
        except Exception as exc:
            logger.debug(f"RedisVS not available: {exc}")
            self._available = False

        return self._available

    # Store chunks and embeddings in Redis.
    async def add(
        self,
        task_id: str,
        chunks: List[str],
        embeddings,
        metadata: Optional[List[Dict[str, Any]]] = None,
        ttl_sec: float = 600.0,
    ) -> None:
        """Save task data in Redis with per-key expiration."""

        if not self.is_available():
            raise RuntimeError("Redis not available")

        import json

        import numpy as np
        import redis as redis_client

        client = redis_client.from_url(self.redis_url)
        pipeline = client.pipeline()
        key_prefix = f"ephemeral:{task_id}"
        metadata_items = metadata or [{} for _ in chunks]

        # Store each chunk as a separate key so TTL is handled natively.
        for index, (chunk, embedding, metadata_item) in enumerate(
            zip(chunks, embeddings, metadata_items)
        ):
            key = f"{key_prefix}:{index}"
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()
            value = json.dumps(
                {
                    "chunk": chunk,
                    "metadata": metadata_item,
                    "embedding": embedding_bytes.hex(),
                }
            )
            pipeline.set(key, value, ex=int(ttl_sec))

        pipeline.set(f"{key_prefix}:count", len(chunks), ex=int(ttl_sec))
        pipeline.execute()

        logger.info(
            f"[Redis] task={task_id}: stored {len(chunks)} chunks, TTL={ttl_sec}s"
        )

    # Search stored Redis embeddings in Python.
    async def search(
        self,
        task_id: str,
        query_embedding,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Return the highest-scoring Redis chunks for a task."""

        if not self.is_available():
            return []

        import json

        import numpy as np
        import redis as redis_client

        client = redis_client.from_url(self.redis_url)
        key_prefix = f"ephemeral:{task_id}"
        count_raw = client.get(f"{key_prefix}:count")
        if not count_raw:
            return []

        count = int(count_raw)
        keys = [f"{key_prefix}:{index}" for index in range(count)]
        values = client.mget(keys)

        query = np.array(query_embedding, dtype=np.float32)
        query /= np.linalg.norm(query) + 1e-9

        results: List[SearchResult] = []
        for value in values:
            if not value:
                continue

            data = json.loads(value)
            embedding = np.frombuffer(
                bytes.fromhex(data["embedding"]),
                dtype=np.float32,
            )
            embedding /= np.linalg.norm(embedding) + 1e-9
            score = float(np.dot(query, embedding))
            results.append(
                SearchResult(
                    chunk=data["chunk"],
                    score=score,
                    metadata=data.get("metadata", {}),
                )
            )

        results.sort(key=lambda result: result.score, reverse=True)
        return results[:top_k]

    # Remove one task from Redis.
    async def purge(self, task_id: str) -> None:
        """Delete all Redis keys associated with one task."""

        if not self.is_available():
            return

        import redis as redis_client

        client = redis_client.from_url(self.redis_url)
        pattern = f"ephemeral:{task_id}:*"
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)

        logger.info(f"[Redis] task={task_id}: purged {len(keys)} keys")


# Backend facade with automatic fallback.
class EphemeralStore:
    # Configure backend selection and TTL defaults.
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefer_redis: bool = True,
        default_ttl_sec: float = 600.0,
    ):
        self._redis_backend = RedisVSBackend(redis_url)
        self._memory_backend = InMemoryVSBackend()
        self._prefer_redis = prefer_redis
        self._default_ttl = default_ttl_sec
        self._backend_name: Optional[str] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    # Choose the active backend.
    def _get_backend(self):
        """Return the preferred available backend."""

        if self._prefer_redis and self._redis_backend.is_available():
            if self._backend_name != "redis":
                logger.info("EphemeralStore: using Redis backend")
                self._backend_name = "redis"
            return self._redis_backend

        if self._backend_name != "memory":
            logger.info("EphemeralStore: using InMemory backend")
            self._backend_name = "memory"

        return self._memory_backend

    # Add task data to the active backend.
    async def add(
        self,
        task_id: str,
        chunks: List[str],
        embeddings,
        metadata: Optional[List[Dict[str, Any]]] = None,
        ttl_sec: Optional[float] = None,
    ) -> None:
        """Store task data using the selected backend."""

        await self._get_backend().add(
            task_id,
            chunks,
            embeddings,
            metadata,
            ttl_sec=ttl_sec or self._default_ttl,
        )

    # Search task data in the active backend.
    async def search(
        self,
        task_id: str,
        query_embedding,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Search the selected backend for task chunks."""

        return await self._get_backend().search(task_id, query_embedding, top_k)

    # Purge task data from all backends.
    async def purge(self, task_id: str) -> None:
        """Delete task data from both backends."""

        await self._memory_backend.purge(task_id)
        try:
            await self._redis_backend.purge(task_id)
        except Exception:
            pass

    # Expose the current backend name.
    @property
    def backend_name(self) -> str:
        self._get_backend()
        return self._backend_name or "unknown"

    # Start the in-memory cleanup loop.
    def start_cleanup_loop(self, interval_sec: float = 60.0) -> None:
        """Start periodic cleanup for expired in-memory entries."""

        # Keep sweeping expired entries while the store is active.
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_sec)
                try:
                    await self._memory_backend.purge_expired()
                except Exception as exc:
                    logger.warning(f"Cleanup loop error: {exc}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    # Stop the in-memory cleanup loop.
    def stop_cleanup_loop(self) -> None:
        """Stop the periodic in-memory cleanup task."""

        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
