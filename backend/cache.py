"""In-memory cache with TTL expiration — simulating Redis for the prototype."""
import time
import threading


class SimpleCache:
    """Thread-safe in-memory cache with per-key TTL expiration.
    Simulates a Redis cache layer for production architecture.
    """

    def __init__(self, default_ttl=60):
        self._store = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key):
        """Get a value from cache. Returns None if expired or not found."""
        with self._lock:
            if key in self._store:
                value, expiry = self._store[key]
                if time.time() < expiry:
                    return value
                del self._store[key]
            return None

    def set(self, key, value, ttl=None):
        """Set a value in cache with optional custom TTL."""
        with self._lock:
            expiry = time.time() + (ttl or self._default_ttl)
            self._store[key] = (value, expiry)

    def invalidate(self, key):
        """Remove a specific key from cache."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix):
        """Remove all keys starting with a prefix."""
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._store[k]

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()

    def stats(self):
        """Return cache statistics."""
        with self._lock:
            now = time.time()
            total = len(self._store)
            active = sum(1 for _, (_, exp) in self._store.items() if exp > now)
            return {"total_keys": total, "active_keys": active, "expired_keys": total - active}


# Global cache instance
cache = SimpleCache(default_ttl=30)
