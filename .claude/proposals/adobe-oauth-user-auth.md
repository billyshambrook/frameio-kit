# Adobe Login OAuth User Authentication for frameio-kit

**Status:** Proposal
**Created:** 2025-10-25
**Author:** Claude (with user requirements)

---

## Executive Summary

This proposal introduces Adobe Login OAuth integration for frameio-kit, enabling custom actions to execute with user-specific tokens rather than server-to-server (S2S) application tokens. This enhancement provides proper user attribution for API calls, aligns with Frame.io's identity model (acquired by Adobe), and creates a better user experience by maintaining authenticated sessions across actions.

**Key Benefits:**
- Actions execute in the user's context with proper attribution
- Transparent OAuth flow with automatic token refresh
- Pluggable storage backends (memory, disk, Redis, etc.)
- Secure token encryption at rest using Fernet
- Opt-in per action with zero impact on existing functionality
- Reusable tokens across multiple actions for the same user

---

## Problem Statement

### Current Limitations

frameio-kit currently requires developers to initialize the client with a Frame.io S2S token:

```python
app = App(token=os.getenv("FRAMEIO_TOKEN"))

@app.on_action("my_app.analyze", "Analyze File", "...", secret)
async def analyze_file(event: ActionEvent):
    # This API call uses the S2S token - NOT associated with the user
    file = await app.client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )
```

**Problems:**
1. **No User Attribution** - API calls appear to come from the application, not the user who triggered the action
2. **Permission Misalignment** - The S2S token may have broader or narrower permissions than the user
3. **Audit Trail Loss** - Cannot track which user performed actions through the integration
4. **Identity Confusion** - Frame.io's activity logs show the application, not the actual user

### User Experience Impact

**Current flow (problematic):**
```
User clicks "Analyze File" → Action executes with S2S token →
Frame.io sees "MyApp" performed the action (not the user)
```

**Desired flow:**
```
User clicks "Analyze File" →
  IF user authenticated → Action executes with user token → Frame.io sees "John Doe" performed the action
  IF not authenticated → User redirected to Adobe Login → Token stored → Action executes
```

---

## Requirements

### Functional Requirements

1. **OAuth Integration**
   - Support Adobe Identity Management System (IMS) OAuth 2.0 flow
   - Handle authorization code exchange for access tokens
   - Automatic token refresh using refresh tokens
   - Secure state management to prevent CSRF attacks

2. **Token Storage**
   - Abstract storage interface for multiple backends
   - Default in-memory storage (no external dependencies)
   - Support for persistent storage (disk, Redis, DynamoDB, etc.)
   - Key tokens by `user_id` from ActionEvent
   - Store access token, refresh token, and expiration metadata

3. **Token Security**
   - Encrypt tokens at rest using Fernet (symmetric encryption)
   - Configurable encryption keys (environment variables in production)
   - Automatic key management via system keyring for development
   - Secure key rotation support

4. **Developer API**
   - App-level OAuth configuration
   - Action-level opt-in via `require_user_auth=True` parameter
   - Built-in OAuth endpoints (`/.auth/login`, `/.auth/callback`) only mounted when auth enabled
   - Automatic token injection into `app.client` for authenticated actions
   - Graceful degradation: return Form with login link if user not authenticated

5. **Token Lifecycle**
   - Automatic refresh before expiration
   - Handle refresh failures gracefully
   - Provide hooks for token events (obtained, refreshed, expired)

### Non-Functional Requirements

1. **Performance**
   - Token retrieval: <10ms (in-memory), <50ms (Redis)
   - Minimal latency overhead for authenticated actions
   - Efficient token refresh (background if possible)

2. **Reliability**
   - Graceful degradation if storage backend unavailable
   - Retry logic for transient OAuth failures
   - Clear error messages for debugging

3. **Security**
   - Follow OAuth 2.0 security best practices (RFC 6749, RFC 6819)
   - Protect against token theft, replay attacks, CSRF
   - Minimal token lifetime (refresh often)
   - Secure secret management

4. **Compatibility**
   - Zero breaking changes to existing API
   - Python 3.13+ (aligned with frameio-kit)
   - Async-first implementation
   - Full type hints for static analysis

5. **Developer Experience**
   - Simple configuration (sensible defaults)
   - Clear documentation with examples
   - Helpful error messages
   - Easy testing (mock storage available)

---

## Technical Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        frameio-kit App                           │
│                                                                  │
│  ┌────────────────┐         ┌──────────────────┐               │
│  │  OAuth Config  │────────▶│  Auth Middleware │               │
│  │  (App level)   │         │                  │               │
│  └────────────────┘         └────────┬─────────┘               │
│                                      │                           │
│                                      ▼                           │
│                           ┌──────────────────┐                  │
│                           │ Token Manager    │                  │
│                           │ - Get/Set Token  │                  │
│                           │ - Refresh Logic  │                  │
│                           └────────┬─────────┘                  │
│                                    │                             │
│                ┌───────────────────┼────────────────┐           │
│                ▼                   ▼                 ▼           │
│         ┌────────────┐      ┌──────────┐    ┌──────────────┐  │
│         │ Encryption │      │ Storage  │    │ OAuth Client │  │
│         │  (Fernet)  │      │ Backend  │    │ (httpx)      │  │
│         └────────────┘      └──────────┘    └──────────────┘  │
│                                    │                             │
└────────────────────────────────────┼─────────────────────────────┘
                                     │
                    ┌────────────────┼───────────────┐
                    ▼                ▼               ▼
              Memory Store     Disk Store      Redis Store
```

### Core Components

#### 1. Storage Layer (py-key-value-aio)

We'll use the [py-key-value-aio](https://github.com/strawgate/py-key-value) library directly, which provides a unified async storage interface with multiple backend implementations:

```python
# src/frameio_kit/_storage.py

from datetime import datetime, timedelta
from pydantic import BaseModel

# Import storage backends from py-key-value-aio
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.disk import DiskStore
# Optional backends:
# from key_value.aio.stores.redis import RedisStore
# from key_value.aio.stores.dynamodb import DynamoDBStore


class TokenData(BaseModel):
    """Token storage model."""
    access_token: str
    refresh_token: str
    expires_at: datetime
    scopes: list[str]
    user_id: str

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired (with 5min buffer for refresh)."""
        return datetime.now() >= (self.expires_at - timedelta(seconds=buffer_seconds))
```

**Available Storage Backends** (from py-key-value-aio):
- **MemoryStore**: Development, single-process apps, ephemeral sessions
- **DiskStore**: Single-server production, persistent sessions
- **RedisStore**: Multi-server production, distributed deployments
- **DynamoDBStore**, **MongoDBStore**, etc.: Cloud-native deployments

**Key Benefits:**
- No custom storage abstraction needed - use battle-tested library
- Consistent async interface across all backends
- Additional backends available without extra code
- Well-maintained by FastMCP team

#### 2. Token Encryption

Using Fernet (symmetric encryption from `cryptography` package):

```python
# src/frameio_kit/_encryption.py

from cryptography.fernet import Fernet
import os
import base64
import json

class TokenEncryption:
    """Encrypts/decrypts tokens using Fernet symmetric encryption."""

    def __init__(self, key: Optional[str] = None) -> None:
        """
        Initialize encryption with a key.

        Args:
            key: Base64-encoded Fernet key. If None, attempts to load from:
                 1. FRAMEIO_AUTH_ENCRYPTION_KEY environment variable
                 2. System keyring (development only)
                 3. Generates ephemeral key (WARNING: tokens lost on restart)
        """
        if key:
            self._key = key.encode() if isinstance(key, str) else key
        elif key_from_env := os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"):
            self._key = key_from_env.encode()
        else:
            # Development: Try to use system keyring, else ephemeral
            self._key = self._get_or_create_dev_key()

        self._fernet = Fernet(self._key)

    def _get_or_create_dev_key(self) -> bytes:
        """Get encryption key from system keyring or create ephemeral one."""
        try:
            import keyring
            key = keyring.get_password("frameio-kit", "auth-encryption-key")
            if key:
                return key.encode()

            # Create and store new key
            key = Fernet.generate_key()
            keyring.set_password("frameio-kit", "auth-encryption-key", key.decode())
            return key
        except ImportError:
            # Keyring not available - use ephemeral key
            import warnings
            warnings.warn(
                "No encryption key configured and keyring unavailable. "
                "Using ephemeral key - tokens will be lost on restart. "
                "Set FRAMEIO_AUTH_ENCRYPTION_KEY in production.",
                UserWarning,
                stacklevel=2
            )
            return Fernet.generate_key()

    def encrypt(self, token_data: TokenData) -> bytes:
        """Encrypt token data to bytes."""
        json_data = token_data.model_dump_json()
        return self._fernet.encrypt(json_data.encode())

    def decrypt(self, encrypted_data: bytes) -> TokenData:
        """Decrypt bytes to token data."""
        decrypted = self._fernet.decrypt(encrypted_data)
        return TokenData.model_validate_json(decrypted)

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key for production use."""
        return Fernet.generate_key().decode()
```

**Security Notes:**
- Production MUST set `FRAMEIO_AUTH_ENCRYPTION_KEY` environment variable
- Development can use system keyring (macOS/Windows) for persistence
- Ephemeral keys will warn developer that tokens are lost on restart
- Keys should be rotated periodically (implement key rotation helper)

#### 3. OAuth Client and Token Manager

```python
# src/frameio_kit/_oauth.py

from typing import Optional, Callable, Awaitable
import httpx
from datetime import datetime, timedelta

class AdobeOAuthClient:
    """Handles Adobe IMS OAuth 2.0 flow."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ["openid", "AdobeID", "frameio.api"]

        # Adobe IMS endpoints
        self.authorization_url = "https://ims-na1.adobelogin.com/ims/authorize/v2"
        self.token_url = "https://ims-na1.adobelogin.com/ims/token/v3"

        self._http = httpx.AsyncClient()

    def get_authorization_url(self, state: str) -> str:
        """Generate OAuth authorization URL for user redirect."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "response_type": "code",
            "state": state,
        }
        return f"{self.authorization_url}?{httpx.QueryParams(params)}"

    async def exchange_code(self, code: str) -> TokenData:
        """Exchange authorization code for access/refresh tokens."""
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        response = await self._http.post(self.token_url, data=data)
        response.raise_for_status()

        token_response = response.json()
        return TokenData(
            access_token=token_response["access_token"],
            refresh_token=token_response["refresh_token"],
            expires_at=datetime.now() + timedelta(seconds=token_response["expires_in"]),
            scopes=token_response.get("scope", "").split(),
            user_id="",  # Will be set by caller
        )

    async def refresh_token(self, refresh_token: str) -> TokenData:
        """Refresh access token using refresh token."""
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        response = await self._http.post(self.token_url, data=data)
        response.raise_for_status()

        token_response = response.json()
        return TokenData(
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token", refresh_token),  # May not return new one
            expires_at=datetime.now() + timedelta(seconds=token_response["expires_in"]),
            scopes=token_response.get("scope", "").split(),
            user_id="",  # Will be set by caller
        )

    async def close(self) -> None:
        await self._http.aclose()


class TokenManager:
    """Manages token lifecycle: storage, retrieval, refresh."""

    def __init__(
        self,
        storage,  # Any py-key-value-aio store
        encryption: TokenEncryption,
        oauth_client: AdobeOAuthClient,
    ) -> None:
        self.storage = storage
        self.encryption = encryption
        self.oauth_client = oauth_client

    def _make_key(self, user_id: str) -> str:
        """Create storage key for user token."""
        return f"user:{user_id}"

    async def get_token(self, user_id: str) -> Optional[TokenData]:
        """
        Get valid token for user, refreshing if necessary.

        Returns None if user has never authenticated.
        Raises exception if refresh fails.
        """
        key = self._make_key(user_id)
        encrypted = await self.storage.get(key)

        if encrypted is None:
            return None

        token_data = self.encryption.decrypt(encrypted)

        # Check if needs refresh
        if token_data.is_expired():
            try:
                token_data = await self._refresh_token(token_data)
                await self.store_token(user_id, token_data)
            except Exception as e:
                # Refresh failed - token may be revoked
                await self.storage.delete(key)
                raise TokenRefreshError(f"Failed to refresh token for user {user_id}") from e

        return token_data

    async def store_token(self, user_id: str, token_data: TokenData) -> None:
        """Store token for user."""
        token_data.user_id = user_id
        key = self._make_key(user_id)
        encrypted = self.encryption.encrypt(token_data)

        # TTL: token lifetime + 1 day buffer for refresh
        ttl = int((token_data.expires_at - datetime.now()).total_seconds()) + 86400

        await self.storage.set(key, encrypted, ttl=ttl)

    async def delete_token(self, user_id: str) -> None:
        """Remove token for user (logout)."""
        key = self._make_key(user_id)
        await self.storage.delete(key)

    async def _refresh_token(self, old_token: TokenData) -> TokenData:
        """Refresh an expired token."""
        new_token = await self.oauth_client.refresh_token(old_token.refresh_token)
        new_token.user_id = old_token.user_id
        return new_token


class TokenRefreshError(Exception):
    """Raised when token refresh fails."""
    pass
```

#### 4. OAuth Endpoints (Starlette Routes)

```python
# src/frameio_kit/_auth_routes.py

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse
import secrets

def create_auth_routes(token_manager: TokenManager, oauth_client: AdobeOAuthClient):
    """Create OAuth endpoint routes."""

    # In-memory state storage (could be Redis in production)
    _oauth_states: dict[str, dict] = {}

    async def login_endpoint(request: Request):
        """Initiate OAuth flow."""
        # Extract user_id and interaction_id from query params
        # These should be passed from the action that needs auth
        user_id = request.query_params.get("user_id")
        interaction_id = request.query_params.get("interaction_id")

        if not user_id:
            return HTMLResponse("Missing user_id parameter", status_code=400)

        # Generate CSRF state token
        state = secrets.token_urlsafe(32)
        _oauth_states[state] = {
            "user_id": user_id,
            "interaction_id": interaction_id,
            "created_at": datetime.now(),
        }

        # Redirect to Adobe OAuth
        auth_url = oauth_client.get_authorization_url(state)
        return RedirectResponse(auth_url)

    async def callback_endpoint(request: Request):
        """Handle OAuth callback."""
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            return HTMLResponse(
                f"<h1>Authentication Failed</h1><p>Error: {error}</p>",
                status_code=400
            )

        if not code or not state:
            return HTMLResponse("Missing code or state parameter", status_code=400)

        # Verify state (CSRF protection)
        state_data = _oauth_states.pop(state, None)
        if not state_data:
            return HTMLResponse("Invalid or expired state", status_code=400)

        # Check state age (max 10 minutes)
        if datetime.now() - state_data["created_at"] > timedelta(minutes=10):
            return HTMLResponse("State expired", status_code=400)

        user_id = state_data["user_id"]

        try:
            # Exchange code for tokens
            token_data = await oauth_client.exchange_code(code)
            await token_manager.store_token(user_id, token_data)

            # Success page (could redirect to Frame.io UI)
            return HTMLResponse(
                """
                <html>
                <head><title>Authentication Successful</title></head>
                <body>
                    <h1>✅ Authentication Successful</h1>
                    <p>You can now close this window and return to Frame.io.</p>
                    <script>
                        setTimeout(() => window.close(), 3000);
                    </script>
                </body>
                </html>
                """
            )
        except Exception as e:
            return HTMLResponse(
                f"<h1>Authentication Failed</h1><p>Error: {str(e)}</p>",
                status_code=500
            )

    return [
        Route("/.auth/login", login_endpoint),
        Route("/.auth/callback", callback_endpoint),
    ]
```

#### 5. Auth Middleware

```python
# src/frameio_kit/_auth_middleware.py

from frameio_kit import Middleware, ActionEvent, AnyEvent, AnyResponse, NextFunc, Message, LinkField, Form

class AuthMiddleware(Middleware):
    """Middleware that injects user tokens for actions requiring auth."""

    def __init__(self, token_manager: TokenManager, base_url: str) -> None:
        self.token_manager = token_manager
        self.base_url = base_url.rstrip("/")

    async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
        """Intercept actions and check if user auth is required."""
        # Check if this action requires user auth (set by decorator)
        requires_auth = getattr(event, "_requires_user_auth", False)

        if not requires_auth:
            # Pass through without auth
            return await next(event)

        # Try to get user token
        user_id = event.user.id
        try:
            token_data = await self.token_manager.get_token(user_id)
        except TokenRefreshError:
            # Refresh failed - need re-auth
            token_data = None

        if token_data is None:
            # User not authenticated - return form with login link
            login_url = f"{self.base_url}/.auth/login?user_id={user_id}&interaction_id={event.interaction_id}"

            return Form(
                title="Authentication Required",
                description="This action requires you to sign in with Adobe.",
                fields=[
                    LinkField(
                        label="Sign in with Adobe",
                        url=login_url,
                        name="_auth_link"
                    )
                ]
            )

        # Attach token to event for handler to use
        event._user_token = token_data.access_token

        return await next(event)
```

#### 6. App Configuration

```python
# src/frameio_kit/_app.py (additions)

class OAuthConfig(BaseModel):
    """OAuth configuration for Adobe IMS."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] = Field(default_factory=lambda: ["openid", "AdobeID", "frameio.api"])

    # Storage configuration - any py-key-value-aio store
    storage: Any = Field(default_factory=lambda: MemoryStore())

    # Encryption key (optional - will auto-generate if not provided)
    encryption_key: Optional[str] = None


class App:
    """The main application class - NOT a Starlette subclass."""

    def __init__(
        self,
        *,
        token: str | Callable[[], str] | None = None,
        middleware: list[Middleware] | None = None,
        oauth: OAuthConfig | None = None,  # NEW
    ):
        # ... existing initialization ...
        self._asgi_app = self._create_asgi_app()  # Internal Starlette instance

        # OAuth setup
        self._oauth_config = oauth
        self._token_manager: Optional[TokenManager] = None

        if oauth:
            # Initialize OAuth components
            encryption = TokenEncryption(key=oauth.encryption_key)
            oauth_client = AdobeOAuthClient(
                client_id=oauth.client_id,
                client_secret=oauth.client_secret,
                redirect_uri=oauth.redirect_uri,
                scopes=oauth.scopes,
            )
            self._token_manager = TokenManager(
                storage=oauth.storage,
                encryption=encryption,
                oauth_client=oauth_client,
            )

            # Mount OAuth routes
            auth_routes = create_auth_routes(self._token_manager, oauth_client)
            self.routes.extend(auth_routes)

            # Add auth middleware
            base_url = oauth.redirect_uri.rsplit("/.auth/callback", 1)[0]
            auth_middleware = AuthMiddleware(self._token_manager, base_url)
            self.user_middleware.insert(0, auth_middleware)

    def on_action(
        self,
        event_type: str,
        name: str,
        description: str,
        secret: str,
        require_user_auth: bool = False,  # NEW
    ):
        """Register custom action handler."""
        def decorator(func):
            # Store auth requirement as metadata
            func._requires_user_auth = require_user_auth

            # ... existing registration logic ...

            return func
        return decorator
```

---

## API Design (Developer Experience)

### Basic Usage (No Changes for Existing Apps)

```python
# Existing apps continue to work without any changes
app = App(token=os.getenv("FRAMEIO_TOKEN"))

@app.on_action("my_app.analyze", "Analyze File", "...", secret)
async def analyze_file(event: ActionEvent):
    # Uses S2S token as before
    file = await app.client.files.show(...)
```

### Opt-In User Authentication

```python
import os
from frameio_kit import App, ActionEvent, OAuthConfig
from key_value.aio.stores.memory import MemoryStore

# Configure OAuth at app level
app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri=os.getenv("ADOBE_REDIRECT_URI"),  # e.g., https://myapp.com/.auth/callback
        storage=MemoryStore(),  # Default - can use DiskStore(), RedisStore(), etc.
    )
)

# Action that requires user authentication
@app.on_action(
    "my_app.share_file",
    name="Share with Team",
    description="Share this file with your team",
    secret=os.getenv("ACTION_SECRET"),
    require_user_auth=True,  # Opt-in to user auth
)
async def share_file(event: ActionEvent):
    # If user is authenticated, this will execute with their token
    # Access user token via event._user_token if needed for external APIs

    # app.client automatically uses user token for this action
    file = await app.client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )

    # ... sharing logic ...

    return Message(title="Shared!", description="File shared with team")
```

### Advanced Storage Configuration

```python
from key_value.aio.stores.redis import RedisStore
from key_value.aio.stores.disk import DiskStore

# Production: Redis for distributed deployments
app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri=os.getenv("ADOBE_REDIRECT_URI"),
        storage=RedisStore(url=os.getenv("REDIS_URL")),
        encryption_key=os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"),  # Must be set in production
    )
)

# Single-server: Persistent disk storage
app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri=os.getenv("ADOBE_REDIRECT_URI"),
        storage=DiskStore(path="/var/lib/frameio_tokens"),
        encryption_key=os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"),
    )
)
```

### Token Access for External APIs

```python
@app.on_action("my_app.sync_to_dropbox", ..., require_user_auth=True)
async def sync_to_dropbox(event: ActionEvent):
    # Access user token if needed for external APIs
    user_token = event._user_token

    # Use with external services that need Frame.io user identity
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.external-service.com/sync",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"file_id": event.resource_id}
        )
```

---

## Implementation Phases

### Phase 1: Core Foundation (Week 1-2)
**Goal:** Token encryption and py-key-value-aio integration

- [ ] Add `py-key-value-aio` dependency
- [ ] Implement token encryption (`TokenEncryption` with Fernet)
- [ ] Add `TokenData` Pydantic model
- [ ] Create wrapper/adapter for py-key-value-aio stores if needed
- [ ] Write comprehensive unit tests for encryption
- [ ] Test integration with MemoryStore and DiskStore from py-key-value-aio
- [ ] Documentation: Storage backends guide (referencing py-key-value-aio)

**Deliverables:**
- `src/frameio_kit/_encryption.py`
- `src/frameio_kit/_storage.py` (TokenData model + any adapters)
- `tests/test_encryption.py`
- `tests/test_storage_integration.py`
- `docs/usage/storage_backends.md`

### Phase 2: OAuth Integration (Week 3-4)
**Goal:** OAuth client and token management

- [ ] Implement `AdobeOAuthClient`
- [ ] Implement `TokenManager` with refresh logic
- [ ] Create OAuth endpoints (`/.auth/login`, `/.auth/callback`)
- [ ] Implement state management for CSRF protection
- [ ] Add `OAuthConfig` Pydantic model
- [ ] Write integration tests with mocked Adobe IMS
- [ ] Documentation: OAuth setup guide

**Deliverables:**
- `src/frameio_kit/_oauth.py`
- `src/frameio_kit/_auth_routes.py`
- `tests/test_oauth.py`
- `docs/usage/oauth_setup.md`

### Phase 3: Middleware Integration (Week 5-6)
**Goal:** Automatic token injection and graceful auth flow

- [ ] Implement `AuthMiddleware`
- [ ] Integrate OAuth config into `App.__init__`
- [ ] Add `require_user_auth` parameter to `@app.on_action`
- [ ] Implement automatic token injection into `app.client`
- [ ] Handle auth failures with Form + login link
- [ ] Write end-to-end tests with mock OAuth server
- [ ] Documentation: User authentication guide with examples

**Deliverables:**
- `src/frameio_kit/_auth_middleware.py`
- Updates to `src/frameio_kit/_app.py`
- Updates to `src/frameio_kit/_client.py` for token injection
- `tests/test_auth_middleware.py`
- `tests/test_integration_oauth.py`
- `docs/usage/user_authentication.md`

### Phase 4: Production Features & Polish (Week 7-8)
**Goal:** Production-ready features and polish

- [ ] Document usage of RedisStore and other py-key-value-aio backends
- [ ] Add token lifecycle hooks (on_token_obtained, on_token_refreshed, on_token_expired)
- [ ] Implement key rotation utilities
- [ ] Add logout/revoke functionality
- [ ] Performance benchmarking and optimization
- [ ] Security audit
- [ ] Complete documentation review
- [ ] Example applications

**Deliverables:**
- `src/frameio_kit/_auth_hooks.py`
- `examples/oauth_app/`
- `examples/oauth_production/` (with Redis)
- `docs/deployment/production_oauth.md`
- `docs/security/token_management.md`

---

## Security Considerations

### Token Storage Security

1. **Encryption at Rest**
   - All tokens encrypted using Fernet symmetric encryption
   - Production MUST provide explicit encryption key via `FRAMEIO_AUTH_ENCRYPTION_KEY`
   - Development uses system keyring (Mac/Windows) or ephemeral keys with warnings

2. **Key Management**
   - Keys stored in environment variables (12-factor app)
   - Never commit keys to source control
   - Rotate keys periodically (provide rotation utility)
   - Support for multiple keys during rotation period

3. **Storage Backend Security**
   - Redis: Use TLS connections in production, authentication required
   - Disk: Restrict file permissions (0600), consider encrypted filesystems
   - Memory: Acceptable for development, not for multi-server production

### OAuth Flow Security

1. **CSRF Protection**
   - Generate cryptographically random state tokens
   - Validate state on callback
   - State expires after 10 minutes
   - Store state with user context to prevent session fixation

2. **Token Lifecycle**
   - Access tokens expire (typically 24 hours for Adobe IMS)
   - Automatic refresh 5 minutes before expiration
   - Refresh tokens stored securely alongside access tokens
   - Failed refresh triggers re-authentication

3. **Network Security**
   - OAuth endpoints MUST be served over HTTPS in production
   - Validate SSL certificates for Adobe IMS requests
   - Use latest TLS versions (1.2+)

### Access Control

1. **Token Scoping**
   - Request minimal scopes needed (`openid`, `AdobeID`, `frameio.api`)
   - Document scope requirements clearly
   - Users can revoke access via Adobe account settings

2. **User Isolation**
   - Tokens keyed by Frame.io user ID from ActionEvent
   - No cross-user token access possible
   - Middleware validates user context before injection

### Incident Response

1. **Token Revocation**
   - Provide admin API to revoke tokens for specific users
   - Support bulk revocation for security incidents
   - Log all token access for auditing

2. **Monitoring**
   - Log authentication failures
   - Alert on repeated refresh failures (possible token theft)
   - Track token usage patterns for anomaly detection

---

## Testing Strategy

### Unit Tests

1. **Storage Integration** (`tests/test_storage_integration.py`)
   - Test integration with py-key-value-aio MemoryStore
   - Test integration with py-key-value-aio DiskStore
   - Test TTL behavior with different backends
   - Test error handling (storage unavailable, etc.)

2. **Encryption** (`tests/test_encryption.py`)
   - Test encrypt/decrypt round-trip
   - Test key generation
   - Test invalid key handling
   - Test different token data structures

3. **OAuth Client** (`tests/test_oauth.py`)
   - Mock Adobe IMS endpoints with `httpx.MockRouter`
   - Test authorization URL generation
   - Test code exchange
   - Test token refresh
   - Test error responses (invalid code, expired token, etc.)

4. **Token Manager** (`tests/test_token_manager.py`)
   - Test token storage and retrieval
   - Test automatic refresh logic
   - Test refresh failure handling
   - Test token expiration edge cases

### Integration Tests

1. **Auth Middleware** (`tests/test_auth_middleware.py`)
   - Test action without auth requirement (pass-through)
   - Test action with auth requirement + valid token
   - Test action with auth requirement + no token (returns Form)
   - Test action with auth requirement + expired token (auto-refresh)
   - Test action with auth requirement + refresh failure (returns Form)

2. **OAuth Flow** (`tests/test_oauth_flow.py`)
   - Full OAuth flow with mock Adobe IMS
   - Test state validation (valid, invalid, expired)
   - Test callback error handling
   - Test CSRF attack prevention

3. **End-to-End** (`tests/test_e2e_oauth.py`)
   - Simulate full action trigger → auth → callback → action completion flow
   - Test token reuse across multiple actions
   - Test concurrent actions with same user token
   - Test token refresh during action execution

### Performance Tests

1. **Storage Benchmarks**
   - Measure get/set latency for each backend
   - Test concurrent access performance
   - Identify bottlenecks

2. **Token Operations**
   - Measure encryption/decryption overhead
   - Measure token refresh latency
   - Ensure <10ms added latency for authenticated actions

### Security Tests

1. **Penetration Testing**
   - Test CSRF attacks on OAuth flow
   - Test token theft scenarios
   - Test replay attacks
   - Verify encryption implementation

2. **Fuzzing**
   - Fuzz OAuth endpoints with malformed inputs
   - Fuzz token data structures
   - Test error handling robustness

---

## Documentation Plan

### User-Facing Documentation

1. **Getting Started with User Auth** (`docs/usage/user_authentication.md`)
   - Why use user tokens vs S2S tokens
   - Basic setup with MemoryStore
   - First authenticated action example
   - Testing locally with ngrok

2. **OAuth Configuration** (`docs/usage/oauth_setup.md`)
   - Adobe IMS app registration
   - Obtaining client ID/secret
   - Configuring redirect URI
   - Environment variable setup

3. **Storage Backends** (`docs/usage/storage_backends.md`)
   - Comparison of storage options
   - When to use each backend
   - Configuration examples for each
   - Migration between backends

4. **Production Deployment** (`docs/deployment/production_oauth.md`)
   - Security checklist
   - Encryption key management
   - HTTPS requirements
   - Monitoring and logging
   - Scaling considerations (Redis for multi-server)

5. **Security Guide** (`docs/security/token_management.md`)
   - Token lifecycle management
   - Key rotation procedures
   - Incident response plan
   - Compliance considerations (GDPR, etc.)

### API Reference Updates

1. **New Classes**
   - `OAuthConfig`
   - `StorageBackend` (and implementations)
   - `TokenEncryption`
   - `TokenData`

2. **Updated Classes**
   - `App.__init__` - add `oauth` parameter
   - `App.on_action` - add `require_user_auth` parameter
   - `ActionEvent` - document `_user_token` attribute

### Example Applications

1. **Simple OAuth App** (`examples/oauth_basic/`)
   - Minimal setup with MemoryStore
   - Single authenticated action
   - Local development instructions

2. **Production OAuth App** (`examples/oauth_production/`)
   - Redis storage
   - Multiple authenticated actions
   - Docker Compose setup
   - Environment variable management

3. **Multi-Storage App** (`examples/oauth_multi_storage/`)
   - Demonstrates all storage backends
   - Configuration switching
   - Performance comparison

---

## Migration Path & Backward Compatibility

### Zero Breaking Changes

- OAuth is entirely opt-in at the app level
- Existing apps without `oauth` parameter work identically
- Actions without `require_user_auth=True` use S2S token as before
- No changes to existing event models or response types

### Migration Steps for Existing Users

1. **Review Current Usage**
   - Identify actions that would benefit from user context
   - Consider which actions need user attribution

2. **Register Adobe IMS Application**
   - Follow Adobe Developer Console guide
   - Obtain client credentials

3. **Add OAuth Configuration**
   ```python
   # Before
   app = App(token=os.getenv("FRAMEIO_TOKEN"))

   # After (existing actions still work)
   app = App(
       token=os.getenv("FRAMEIO_TOKEN"),  # Keep for non-auth actions
       oauth=OAuthConfig(...)              # Add for auth actions
   )
   ```

4. **Opt-In Actions Gradually**
   - Add `require_user_auth=True` to selected actions
   - Test each action thoroughly
   - Monitor authentication success rates

5. **Choose Storage Backend**
   - Start with MemoryStore for testing
   - Move to DiskStore for single-server production
   - Scale to RedisStore for multi-server deployments

### Deprecation Timeline

No deprecations planned. S2S tokens remain fully supported for:
- Webhook handlers (no user context available)
- Actions that don't need user attribution
- Applications that prefer simpler setup

---

## Dependencies

### New Required Dependencies

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "cryptography>=44.0.0",      # Fernet encryption
    "py-key-value-aio>=0.1.0",   # Unified async storage interface
]
```

### New Optional Dependencies

```toml
[project.optional-dependencies]
# py-key-value-aio backends are optional - users install as needed
# Examples:
# redis = ["py-key-value-aio[redis]"]
# dynamodb = ["py-key-value-aio[dynamodb]"]

dev = [
    # ... existing dev dependencies ...
    "keyring>=25.6.0",           # System keyring for dev key storage (optional)
]
```

**Rationale:**
- `cryptography`: Industry-standard encryption library, minimal footprint (~3MB)
- `py-key-value-aio`: Battle-tested storage abstraction used by FastMCP (minimal core, ~100KB)
- `keyring`: Optional for better dev experience (persistent keys across restarts)
- Backend-specific dependencies (Redis, DynamoDB, etc.) installed only when needed

**Total Impact:**
- Required: +2 core dependencies (cryptography + py-key-value-aio, ~3.1MB total)
- Optional: Backend dependencies only when needed
- Removes need for ~200 lines of custom storage code
- Aligned with "minimal dependencies" principle

---

## Open Questions & Future Enhancements

### Open Questions

1. **Token Cleanup**
   - Should we auto-delete tokens after X days of inactivity?
   - How to handle user deletions in Frame.io?

2. **Multi-Tenancy**
   - Should storage keys include account_id for isolation?
   - How to support multiple Frame.io accounts per deployment?

3. **Token Scope Management**
   - Should different actions request different scopes?
   - How to handle scope expansion without re-auth?

4. **Offline Token Validation**
   - Should we validate token signatures locally (if Adobe provides public keys)?
   - Or always trust stored tokens until refresh fails?

### Future Enhancements

1. **Additional Storage Backends**
   - All py-key-value-aio backends automatically supported (PostgreSQL, MongoDB, DynamoDB, etc.)
   - No additional code needed - just documentation

2. **Token Introspection**
   - Admin API to view active tokens
   - User count, last access times
   - Token health dashboard

3. **Advanced Auth Features**
   - Service account impersonation
   - Token delegation for background jobs
   - SSO integration for enterprise customers

4. **Developer Tools**
   - CLI tool for token management
   - Debug middleware to simulate auth states
   - Token expiration simulator for testing

---

## Success Criteria

### Technical Metrics

- [ ] Zero breaking changes to existing API
- [ ] <10ms latency overhead for authenticated actions (in-memory storage)
- [ ] <50ms latency overhead for authenticated actions (Redis storage)
- [ ] 100% test coverage for new auth components
- [ ] Pass all security audit checks
- [ ] Full type hints with pyrefly strict mode

### User Experience Metrics

- [ ] OAuth setup completable in <15 minutes (with docs)
- [ ] Clear error messages guide developers to solutions
- [ ] Example apps deployable in <5 minutes
- [ ] Positive feedback from beta testers on DX

### Documentation Metrics

- [ ] 100% of public API documented with Google-style docstrings
- [ ] All use cases covered in guides
- [ ] Security best practices clearly documented
- [ ] Migration path tested with real users

---

## Conclusion

This proposal introduces Adobe Login OAuth user authentication to frameio-kit in a way that:

1. **Preserves Simplicity** - Opt-in design means existing apps continue to work without changes
2. **Follows Principles** - Async-first, type-safe, minimal dependencies, excellent DX
3. **Scales Appropriately** - From in-memory dev setups to Redis-backed production deployments
4. **Prioritizes Security** - Encryption at rest, CSRF protection, minimal token lifetime
5. **Enables User Context** - Actions execute with proper user attribution for better audit trails

The phased implementation allows for iterative development, testing, and feedback. By Week 8, frameio-kit will support best-in-class user authentication while maintaining its core value proposition: the fastest way to build Frame.io integrations.

---

**Next Steps:**
1. Review and approve this proposal
2. Create GitHub issue for community feedback
3. Begin Phase 1 implementation
4. Beta test with select users
5. General availability release
