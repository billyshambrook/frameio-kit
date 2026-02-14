"""Storage protocol and built-in implementations for token persistence.

This module defines the Storage protocol for key-value storage backends
and provides a MemoryStorage implementation for development use.
"""

import time
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    """Protocol for async key-value storage backends.

    Implementations must support get, put, and delete operations with
    optional TTL (time-to-live) support for automatic expiration.

    Example:
        ```python
        class MyStorage:
            async def get(self, key: str) -> dict[str, Any] | None:
                ...

            async def put(self, key: str, value: dict[str, Any], *, ttl: int | None = None) -> None:
                ...

            async def delete(self, key: str) -> None:
                ...
        ```
    """

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a value by key.

        Args:
            key: The storage key.

        Returns:
            The stored dictionary, or None if the key does not exist or has expired.
        """
        ...

    async def put(self, key: str, value: dict[str, Any], *, ttl: int | None = None) -> None:
        """Store a value with an optional TTL.

        Args:
            key: The storage key.
            value: The dictionary value to store.
            ttl: Optional time-to-live in seconds. If None, the value does not expire.
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete a value by key.

        Args:
            key: The storage key. No error is raised if the key does not exist.
        """
        ...


class MemoryStorage:
    """In-memory storage backend for development and testing.

    Values are stored in a dictionary with optional TTL support using
    monotonic time. Expired entries are lazily cleaned up on access.

    Example:
        ```python
        storage = MemoryStorage()
        await storage.put("key", {"data": "value"}, ttl=3600)
        result = await storage.get("key")
        ```
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[dict[str, Any], float | None]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if expiry is not None and time.monotonic() >= expiry:
            del self._data[key]
            return None
        return value

    async def put(self, key: str, value: dict[str, Any], *, ttl: int | None = None) -> None:
        expiry = time.monotonic() + ttl if ttl is not None else None
        self._data[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
