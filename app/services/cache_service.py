"""Redis cache service for query results."""

import json
import hashlib
from typing import Optional, Any
from redis import asyncio as aioredis
from app.config import settings


class CacheService:
    """Service for caching query results in Redis."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis: Optional[aioredis.Redis] = None
        self.enabled = settings.ENABLE_CACHE
        self.ttl = settings.CACHE_TTL
    
    async def connect(self):
        """Establish Redis connection."""
        if self.enabled:
            try:
                self.redis = await aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Verify connection is actually reachable
                await self.redis.ping()
            except Exception as e:
                print(f"Warning: Redis connection failed: {e}. Cache disabled.")
                self.redis = None
                self.enabled = False
    
    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
    
    def _generate_cache_key(self, dataset_id: str, question: str) -> str:
        """
        Generate a cache key for a query.
        
        Args:
            dataset_id: Dataset UUID
            question: User question
            
        Returns:
            Cache key (MD5 hash)
        """
        key_string = f"{dataset_id}:{question.lower().strip()}"
        return f"query:{hashlib.md5(key_string.encode()).hexdigest()}"
    
    async def get(self, dataset_id: str, question: str) -> Optional[dict]:
        """
        Retrieve cached query result.
        
        Args:
            dataset_id: Dataset UUID
            question: User question
            
        Returns:
            Cached result or None
        """
        if not self.enabled or not self.redis:
            return None
        
        try:
            cache_key = self._generate_cache_key(dataset_id, question)
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
        except Exception as e:
            print(f"Cache get error: {e}")
            self.redis = None
            self.enabled = False
            return None
    
    async def set(self, dataset_id: str, question: str, result: dict) -> bool:
        """
        Cache a query result.
        
        Args:
            dataset_id: Dataset UUID
            question: User question
            result: Query result to cache
            
        Returns:
            True if cached successfully, False otherwise
        """
        if not self.enabled or not self.redis:
            return False
        
        try:
            cache_key = self._generate_cache_key(dataset_id, question)
            cached_data = json.dumps(result)
            
            await self.redis.setex(
                cache_key,
                self.ttl,
                cached_data
            )
            
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
            self.redis = None
            self.enabled = False
            return False
    
    async def invalidate_dataset(self, dataset_id: str) -> bool:
        """
        Invalidate all cache entries for a dataset.
        
        Args:
            dataset_id: Dataset UUID
            
        Returns:
            True if invalidated successfully
        """
        if not self.enabled or not self.redis:
            return False
        
        try:
            # Find all keys matching the dataset
            pattern = f"query:*{dataset_id}*"
            keys = []
            
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await self.redis.delete(*keys)
            
            return True
        except Exception as e:
            print(f"Cache invalidation error: {e}")
            return False


# Global cache service instance
cache_service = CacheService()
