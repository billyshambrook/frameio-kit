from typing import Callable

import httpx
from frameio import AsyncFrameio
from frameio_experimental import AsyncFrameioExperimental


class Client(AsyncFrameio):
    """Asynchronous HTTP client for interacting with the Frame.io v4 API.

    This class provides access to all stable API endpoints and also contains a
    dedicated client for experimental features via the `.experimental` property.

    Attributes:
        experimental: An instance of `ExperimentalFrameioClient` for accessing
            endpoints that are in beta or under development.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | Callable[[], str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        follow_redirects: bool | None = True,
    ):
        self._httpx_client = httpx.AsyncClient()

        super().__init__(
            base_url=base_url,
            token=token,
            headers=headers,
            timeout=timeout,
            follow_redirects=follow_redirects,
            httpx_client=self._httpx_client,
        )
        _base_experimental_headers = {"api-version": "experimental"}
        experimental_headers = _base_experimental_headers.copy()
        if headers:
            experimental_headers.update(headers)

        self._experimental = AsyncFrameioExperimental(
            base_url=base_url,
            token=token,
            headers=experimental_headers,
            timeout=timeout,
            follow_redirects=follow_redirects,
            httpx_client=self._httpx_client,
        )

    async def close(self) -> None:
        """Gracefully closes the underlying `httpx.AsyncClient` session."""
        if not self._httpx_client.is_closed:
            await self._httpx_client.aclose()
