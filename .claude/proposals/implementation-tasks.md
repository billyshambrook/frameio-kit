# Adobe Login OAuth Implementation - Task Breakdown

**Status:** Ready for execution
**Created:** 2025-10-25
**Total Tasks:** 28 tasks across 4 phases (8 weeks)

---

## **Phase 1: Foundation (Weeks 1-2)**
**Goal:** Token storage and encryption infrastructure

### Task 1.1: Add py-key-value-aio dependency
**Deliverable:** Updated `pyproject.toml` with py-key-value-aio dependency

**Acceptance Criteria:**
- [ ] Add `py-key-value-aio>=0.1.0` to dependencies in pyproject.toml
- [ ] Run `uv sync` to install
- [ ] Verify import works: `from key_value.aio.stores.memory import MemoryStore`

---

### Task 1.2: Create TokenData model
**Deliverable:** `src/frameio_kit/_storage.py` with TokenData Pydantic model

**Acceptance Criteria:**
- [ ] Define `TokenData` class extending BaseModel
- [ ] Include fields: `access_token`, `refresh_token`, `expires_at`, `scopes`, `user_id`
- [ ] Add `is_expired(buffer_seconds: int = 300)` method
- [ ] Include full type hints and Google-style docstrings
- [ ] Import statement at top: `from datetime import datetime, timedelta`

---

### Task 1.3: Implement TokenEncryption class
**Deliverable:** `src/frameio_kit/_encryption.py` with Fernet-based encryption

**Acceptance Criteria:**
- [ ] Add `cryptography>=44.0.0` to dependencies in pyproject.toml
- [ ] Implement `TokenEncryption` class
- [ ] Add `__init__(key: Optional[str] = None)` method with key loading hierarchy:
  - From parameter
  - From FRAMEIO_AUTH_ENCRYPTION_KEY env var
  - From system keyring (dev only)
  - Generate ephemeral (with warning)
- [ ] Implement `encrypt(token_data: TokenData) -> bytes`
- [ ] Implement `decrypt(encrypted_data: bytes) -> TokenData`
- [ ] Add static method `generate_key() -> str`
- [ ] Include comprehensive docstrings

---

### Task 1.4: Write encryption unit tests
**Deliverable:** `tests/test_encryption.py` with comprehensive test coverage

**Acceptance Criteria:**
- [ ] Test encrypt/decrypt round-trip (valid token data)
- [ ] Test key generation produces valid Fernet keys
- [ ] Test invalid key handling (raises exception)
- [ ] Test TokenData serialization/deserialization edge cases
- [ ] Test key loading from environment variable (mock)
- [ ] Test ephemeral key generation (mock keyring unavailable)
- [ ] Achieve 100% coverage for `_encryption.py`
- [ ] All tests pass with `pytest tests/test_encryption.py`

---

### Task 1.5: Write storage integration tests
**Deliverable:** `tests/test_storage_integration.py`

**Acceptance Criteria:**
- [ ] Test MemoryStore integration (get/set/delete with encrypted data)
- [ ] Test DiskStore integration
- [ ] Test TTL expiration behavior (tokens auto-delete after TTL)
- [ ] Test concurrent access patterns (multiple async operations)
- [ ] Test get() returns None for non-existent keys
- [ ] Test get() returns None for expired keys
- [ ] Mock py-key-value-aio stores for predictable testing
- [ ] All tests pass with `pytest tests/test_storage_integration.py`

---

### Task 1.6: Document storage backends
**Deliverable:** `docs/usage/storage_backends.md`

**Acceptance Criteria:**
- [ ] Explain MemoryStore (default, ephemeral, development)
- [ ] Explain DiskStore (persistent, single-server production)
- [ ] Explain RedisStore (distributed, multi-server production)
- [ ] Include configuration code examples for each backend
- [ ] Add comparison table (persistence, performance, use cases)
- [ ] Link to py-key-value-aio documentation for advanced backends
- [ ] Include troubleshooting section
- [ ] Add to mkdocs.yml navigation

---

## **Phase 2: OAuth Integration (Weeks 3-4)**
**Goal:** Adobe IMS OAuth client and token management

### Task 2.1: Create OAuthConfig Pydantic model
**Deliverable:** Update `src/frameio_kit/_app.py` with OAuthConfig class

**Acceptance Criteria:**
- [ ] Define `OAuthConfig` class extending BaseModel
- [ ] Add fields: `client_id: str`, `client_secret: str`, `redirect_uri: str`
- [ ] Add field: `scopes: list[str]` with default `["openid", "AdobeID", "frameio.api"]`
- [ ] Add field: `storage: Any` with default factory `MemoryStore()`
- [ ] Add field: `encryption_key: Optional[str] = None`
- [ ] Add field validators for required fields
- [ ] Include comprehensive docstrings
- [ ] Full type hints compatible with pyrefly

---

### Task 2.2: Implement AdobeOAuthClient
**Deliverable:** `src/frameio_kit/_oauth.py` with OAuth client class

**Acceptance Criteria:**
- [ ] Create new file `src/frameio_kit/_oauth.py`
- [ ] Define `AdobeOAuthClient` class
- [ ] Add `__init__` with parameters: client_id, client_secret, redirect_uri, scopes
- [ ] Set Adobe IMS endpoints:
  - authorization_url: `https://ims-na1.adobelogin.com/ims/authorize/v2`
  - token_url: `https://ims-na1.adobelogin.com/ims/token/v3`
- [ ] Implement `get_authorization_url(state: str) -> str`
- [ ] Implement `async exchange_code(code: str) -> TokenData`
- [ ] Implement `async refresh_token(refresh_token: str) -> TokenData`
- [ ] Use `httpx.AsyncClient` for all HTTP requests
- [ ] Add `async close()` method for cleanup
- [ ] Include error handling for OAuth failures (raise exceptions with clear messages)
- [ ] Full type hints and docstrings

---

### Task 2.3: Implement TokenManager
**Deliverable:** Add TokenManager class to `src/frameio_kit/_oauth.py`

**Acceptance Criteria:**
- [ ] Define `TokenManager` class in `_oauth.py`
- [ ] Add `__init__` accepting: storage, encryption, oauth_client
- [ ] Implement `async get_token(user_id: str) -> Optional[TokenData]`
  - Returns None if never authenticated
  - Auto-refreshes if expired
  - Raises TokenRefreshError if refresh fails
- [ ] Implement `async store_token(user_id: str, token_data: TokenData) -> None`
  - Encrypts token before storage
  - Sets appropriate TTL
- [ ] Implement `async delete_token(user_id: str) -> None`
- [ ] Implement private `async _refresh_token(old_token: TokenData) -> TokenData`
- [ ] Implement `_make_key(user_id: str) -> str` (format: "user:{user_id}")
- [ ] Define `TokenRefreshError` exception class
- [ ] Full type hints and docstrings

---

### Task 2.4: Create OAuth login endpoint
**Deliverable:** `src/frameio_kit/_auth_routes.py` with login route

**Acceptance Criteria:**
- [ ] Create new file `src/frameio_kit/_auth_routes.py`
- [ ] Define `create_auth_routes(token_manager, oauth_client)` function
- [ ] Implement `async login_endpoint(request: Request)` handler
- [ ] Extract user_id and interaction_id from query params
- [ ] Return 400 if user_id missing
- [ ] Generate CSRF state token using `secrets.token_urlsafe(32)`
- [ ] Store state in-memory dict with user context and timestamp
- [ ] Generate authorization URL via oauth_client
- [ ] Return RedirectResponse to Adobe
- [ ] Include comprehensive docstrings

---

### Task 2.5: Create OAuth callback endpoint
**Deliverable:** Add callback route to `src/frameio_kit/_auth_routes.py`

**Acceptance Criteria:**
- [ ] Implement `async callback_endpoint(request: Request)` handler
- [ ] Extract code, state, error from query params
- [ ] Return 400 HTML page if error present
- [ ] Validate state token (CSRF protection)
- [ ] Return 400 if state invalid or expired (>10 min)
- [ ] Exchange code for tokens via oauth_client
- [ ] Store encrypted tokens via token_manager
- [ ] Return success HTML page with:
  - Success message
  - Auto-close script (3 second timeout)
- [ ] Handle exceptions gracefully (500 page with error details)
- [ ] Return list of Route objects from create_auth_routes()

---

### Task 2.6: Write OAuth client unit tests
**Deliverable:** `tests/test_oauth.py`

**Acceptance Criteria:**
- [ ] Mock Adobe IMS endpoints using `httpx.MockRouter`
- [ ] Test `get_authorization_url()` generates correct URL with params
- [ ] Test `exchange_code()` success (returns valid TokenData)
- [ ] Test `exchange_code()` failure (raises exception)
- [ ] Test `refresh_token()` success (returns new TokenData)
- [ ] Test `refresh_token()` failure (raises exception)
- [ ] Test error handling for network errors
- [ ] 100% coverage for AdobeOAuthClient
- [ ] All tests pass with `pytest tests/test_oauth.py`

---

### Task 2.7: Write TokenManager unit tests
**Deliverable:** `tests/test_token_manager.py`

**Acceptance Criteria:**
- [ ] Mock storage backend for controlled testing
- [ ] Mock encryption for speed
- [ ] Mock oauth_client for refresh operations
- [ ] Test `get_token()` when user never authenticated (returns None)
- [ ] Test `get_token()` with valid token (returns token)
- [ ] Test `get_token()` with expired token (auto-refreshes, returns new token)
- [ ] Test `get_token()` with refresh failure (raises TokenRefreshError, deletes token)
- [ ] Test `store_token()` encrypts and stores correctly
- [ ] Test `delete_token()` removes from storage
- [ ] Test `_make_key()` generates correct key format
- [ ] Test TTL calculation
- [ ] All tests pass with `pytest tests/test_token_manager.py`

---

### Task 2.8: Write OAuth flow integration tests
**Deliverable:** `tests/test_oauth_flow.py`

**Acceptance Criteria:**
- [ ] Use Starlette TestClient for HTTP simulation
- [ ] Mock Adobe IMS server responses
- [ ] Test complete flow: GET /auth/login → redirect → GET /auth/callback → success
- [ ] Test state validation (valid state works)
- [ ] Test state validation (invalid state returns 400)
- [ ] Test state validation (expired state returns 400)
- [ ] Test CSRF attack prevention (reused state fails)
- [ ] Test error from Adobe (error query param)
- [ ] Test missing code parameter
- [ ] Test callback error handling (exception during token exchange)
- [ ] All tests pass with `pytest tests/test_oauth_flow.py`

---

### Task 2.9: Document OAuth setup
**Deliverable:** `docs/usage/oauth_setup.md`

**Acceptance Criteria:**
- [ ] Section: "Registering Adobe IMS Application"
  - Link to Adobe Developer Console
  - Step-by-step with screenshots or detailed instructions
- [ ] Section: "Obtaining Credentials"
  - Where to find client_id
  - Where to find client_secret
  - Security warning about secret handling
- [ ] Section: "Configuring Redirect URI"
  - Format: `https://your-domain.com/.auth/callback`
  - Local development: `http://localhost:8000/.auth/callback`
- [ ] Section: "Environment Variables"
  - Code example showing .env file
  - ADOBE_CLIENT_ID, ADOBE_CLIENT_SECRET, ADOBE_REDIRECT_URI
- [ ] Section: "Testing Locally with ngrok"
  - How to expose localhost
  - Updating redirect_uri in Adobe console
- [ ] Section: "Troubleshooting"
  - Common errors and solutions
- [ ] Add to mkdocs.yml navigation

---

## **Phase 3: Middleware Integration (Weeks 5-6)**
**Goal:** Automatic token injection and seamless user experience

### Task 3.1: Implement AuthMiddleware
**Deliverable:** `src/frameio_kit/_auth_middleware.py` with middleware class

**Acceptance Criteria:**
- [ ] Create new file `src/frameio_kit/_auth_middleware.py`
- [ ] Import base Middleware class
- [ ] Define `AuthMiddleware` class extending Middleware
- [ ] Add `__init__(token_manager: TokenManager, base_url: str)`
- [ ] Override `async on_action(event: ActionEvent, next: NextFunc) -> AnyResponse`
- [ ] Check if handler has `_requires_user_auth` attribute
- [ ] If not required, call `next(event)` immediately (pass-through)
- [ ] If required:
  - Get user_id from event.user.id
  - Try to get token via token_manager.get_token(user_id)
  - If token exists: attach as event._user_token, call next(event)
  - If token None: return Form with login link
  - Handle TokenRefreshError: return Form with login link
- [ ] Implement helper `_create_login_form(login_url: str) -> Form`
- [ ] Full type hints and docstrings

---

### Task 3.2: Update App.__init__ for OAuth
**Deliverable:** Updated `src/frameio_kit/_app.py` with OAuth initialization

**Acceptance Criteria:**
- [ ] Add `oauth: OAuthConfig | None = None` parameter to `App.__init__`
- [ ] Store as `self._oauth_config`
- [ ] Initialize `self._token_manager: Optional[TokenManager] = None`
- [ ] If oauth provided:
  - Create TokenEncryption instance
  - Create AdobeOAuthClient instance
  - Create TokenManager instance
  - Import create_auth_routes from _auth_routes
  - Call create_auth_routes(token_manager, oauth_client)
  - Mount routes to self._asgi_app (extend routes list)
  - Create AuthMiddleware instance
  - Insert at start of middleware chain: `self._middleware.insert(0, auth_middleware)`
- [ ] Extract base_url from redirect_uri for AuthMiddleware
- [ ] Update _lifespan to close oauth_client if needed
- [ ] Full type hints

---

### Task 3.3: Add require_user_auth parameter to on_action
**Deliverable:** Updated `on_action` decorator in `src/frameio_kit/_app.py`

**Acceptance Criteria:**
- [ ] Add parameter `require_user_auth: bool = False` to on_action signature
- [ ] Store as attribute on function: `func._requires_user_auth = require_user_auth`
- [ ] Update docstring to document new parameter
- [ ] Include example showing `require_user_auth=True`
- [ ] Verify backward compatibility (existing code without param still works)

---

### Task 3.4: Implement token injection into Client
**Deliverable:** Updated `src/frameio_kit/_client.py` for dynamic tokens

**Acceptance Criteria:**
- [ ] Review existing Client implementation (already supports callable tokens)
- [ ] Verify token can be dynamically provided per-request
- [ ] Update app.client initialization to check for event._user_token
- [ ] If event has _user_token, use that; else use app._token
- [ ] Ensure thread-safety for concurrent requests
- [ ] Add test to verify token injection works
- [ ] Document in Client docstring

---

### Task 3.5: Create login Form/Message helpers
**Deliverable:** Helper utilities in `src/frameio_kit/_auth_middleware.py`

**Acceptance Criteria:**
- [ ] Implement `_create_login_form(login_url: str) -> Form`
- [ ] Use clear title: "Authentication Required"
- [ ] Use clear description explaining why auth is needed
- [ ] Include LinkField with label "Sign in with Adobe"
- [ ] Properly encode URL parameters (user_id, interaction_id)
- [ ] Return Form instance ready to be returned from middleware

---

### Task 3.6: Write AuthMiddleware unit tests
**Deliverable:** `tests/test_auth_middleware.py`

**Acceptance Criteria:**
- [ ] Mock TokenManager for controlled testing
- [ ] Test action without auth requirement (pass-through to next())
- [ ] Test action with auth + valid token (token attached to event, next() called)
- [ ] Test action with auth + no token (returns Form with login link)
- [ ] Test action with auth + expired token that refreshes successfully
- [ ] Test action with auth + expired token that fails refresh (returns Form)
- [ ] Verify login URL format in returned Form
- [ ] All tests pass with `pytest tests/test_auth_middleware.py`

---

### Task 3.7: Write end-to-end integration tests
**Deliverable:** `tests/test_e2e_oauth.py`

**Acceptance Criteria:**
- [ ] Set up full App with OAuth config
- [ ] Mock Adobe IMS server
- [ ] Test full flow:
  1. Trigger action requiring auth (no token) → returns Form
  2. Follow login link → redirected to Adobe (mocked)
  3. Adobe redirects to callback with code
  4. Token stored
  5. Re-trigger action → executes with user token
- [ ] Test token reuse: trigger second action without re-auth
- [ ] Test concurrent actions with same user (both get same token)
- [ ] Test token refresh during action execution
- [ ] All tests pass with `pytest tests/test_e2e_oauth.py`

---

### Task 3.8: Update public exports
**Deliverable:** Updated `src/frameio_kit/__init__.py`

**Acceptance Criteria:**
- [ ] Add OAuthConfig to imports
- [ ] Add TokenRefreshError to imports (if public)
- [ ] Update __all__ list with new exports
- [ ] Verify backward compatibility (all existing exports still work)
- [ ] Run `python -c "from frameio_kit import *; print(dir())"` to verify

---

### Task 3.9: Document user authentication
**Deliverable:** `docs/usage/user_authentication.md`

**Acceptance Criteria:**
- [ ] Section: "Why User Tokens vs S2S"
  - Explain attribution benefits
  - Explain audit trail
  - When to use each
- [ ] Section: "Quick Start"
  - Complete minimal example (10-15 lines)
  - Show OAuthConfig setup
  - Show require_user_auth=True usage
- [ ] Section: "How It Works"
  - Explain OAuth flow diagram
  - Explain token storage and refresh
- [ ] Section: "Testing the Flow"
  - Local development setup
  - Using ngrok for OAuth callback
- [ ] Section: "Common Patterns"
  - Mixing S2S and user auth actions
  - Accessing user token for external APIs
- [ ] Section: "Troubleshooting"
  - Common errors and solutions
- [ ] Add to mkdocs.yml navigation

---

## **Phase 4: Production Polish (Weeks 7-8)**
**Goal:** Production-ready features and documentation

### Task 4.1: Document Redis deployment
**Deliverable:** `docs/deployment/production_oauth.md`

**Acceptance Criteria:**
- [ ] Section: "Production Security Checklist"
  - HTTPS requirement
  - Encryption key management
  - Secret storage (not in code)
  - State storage considerations
- [ ] Section: "Redis Configuration"
  - Code example with RedisStore
  - Redis connection URL format
  - Redis authentication
  - TLS for Redis connections
- [ ] Section: "Encryption Key Management"
  - Generating keys: TokenEncryption.generate_key()
  - Storing in environment variables
  - Key rotation process
- [ ] Section: "Monitoring and Logging"
  - What to log (auth events, refresh failures)
  - What NOT to log (tokens, secrets)
  - Alerting recommendations
- [ ] Section: "Multi-Server Deployment"
  - Why Redis is needed
  - Session persistence across servers
  - Load balancer configuration
- [ ] Add to mkdocs.yml navigation

---

### Task 4.2: Document token security
**Deliverable:** `docs/security/token_management.md`

**Acceptance Criteria:**
- [ ] Section: "Token Lifecycle"
  - How tokens are obtained
  - How tokens are stored (encrypted)
  - How tokens are refreshed
  - How tokens are revoked
- [ ] Section: "Encryption Key Rotation"
  - Step-by-step rotation procedure
  - Zero-downtime rotation strategy
  - Testing rotation
- [ ] Section: "Incident Response"
  - What to do if key compromised
  - Bulk token revocation
  - User notification
- [ ] Section: "Compliance Considerations"
  - GDPR (data storage, user rights)
  - Data retention policies
  - Token deletion on user request
- [ ] Section: "Security Best Practices"
  - HTTPS only in production
  - Secret management
  - State expiration
  - Rate limiting considerations
- [ ] Add to mkdocs.yml navigation

---

### Task 4.3: Create basic OAuth example app
**Deliverable:** `examples/oauth_basic/`

**Acceptance Criteria:**
- [ ] Create directory structure:
  - `examples/oauth_basic/main.py`
  - `examples/oauth_basic/README.md`
  - `examples/oauth_basic/.env.example`
- [ ] main.py contains:
  - Minimal working app (< 30 lines)
  - One action with require_user_auth=True
  - MemoryStore configuration
  - Clear comments
- [ ] README.md includes:
  - Prerequisites
  - Setup instructions
  - How to get Adobe credentials
  - How to run locally with ngrok
  - Testing the auth flow
- [ ] .env.example shows required variables
- [ ] Verify example runs successfully

---

### Task 4.4: Create production OAuth example
**Deliverable:** `examples/oauth_production/`

**Acceptance Criteria:**
- [ ] Create directory structure:
  - `examples/oauth_production/main.py`
  - `examples/oauth_production/README.md`
  - `examples/oauth_production/.env.example`
  - `examples/oauth_production/docker-compose.yml`
  - `examples/oauth_production/Dockerfile`
- [ ] main.py contains:
  - Production-ready configuration
  - RedisStore usage
  - Multiple authenticated actions
  - Error handling
  - Logging
- [ ] docker-compose.yml includes:
  - App service
  - Redis service
  - Volume mounts
  - Environment variables
- [ ] README.md includes:
  - Production deployment guide
  - Docker setup instructions
  - Environment variable configuration
  - Health checks
  - Monitoring recommendations
- [ ] Verify example runs with docker-compose up

---

### Task 4.5: Add token lifecycle hooks (optional)
**Deliverable:** `src/frameio_kit/_auth_hooks.py` (if time allows)

**Acceptance Criteria:**
- [ ] Define hook interface (Protocol or ABC)
- [ ] Define hooks: on_token_obtained, on_token_refreshed, on_token_expired
- [ ] Update TokenManager to accept hooks parameter
- [ ] Call hooks at appropriate times
- [ ] Add tests for hook invocation
- [ ] Document usage in oauth_setup.md
- [ ] Example: logging, metrics, notifications

---

### Task 4.6: Performance benchmarking
**Deliverable:** `tests/benchmark_oauth.py` + performance report

**Acceptance Criteria:**
- [ ] Benchmark encryption/decryption (100+ iterations)
- [ ] Benchmark MemoryStore operations (get/set/delete)
- [ ] Benchmark DiskStore operations
- [ ] Benchmark Redis operations (if available)
- [ ] Benchmark end-to-end auth middleware overhead
- [ ] Verify <10ms overhead for MemoryStore
- [ ] Verify <50ms overhead for Redis
- [ ] Document results in proposal (append section)
- [ ] Create graphs/charts if helpful

---

### Task 4.7: Security audit
**Deliverable:** Security audit checklist + fixes

**Acceptance Criteria:**
- [ ] Review CSRF protection:
  - State generation is cryptographically random
  - State is validated on callback
  - State expires (10 min max)
  - State is single-use
- [ ] Review token encryption:
  - Fernet implementation correct
  - Keys properly managed
  - Keys never logged
- [ ] Review OAuth implementation:
  - Redirect URI validation
  - Code exchange follows best practices
  - Token storage is secure
- [ ] Test common vulnerabilities:
  - CSRF attacks (blocked)
  - Token theft (encrypted at rest)
  - Replay attacks (state single-use)
- [ ] Document findings in security audit report
- [ ] Fix any issues discovered
- [ ] Re-test after fixes

---

### Task 4.8: Update API reference docs
**Deliverable:** Updated `docs/api_reference.md`

**Acceptance Criteria:**
- [ ] Ensure mkdocstrings-python configured in mkdocs.yml
- [ ] Add section for OAuthConfig class (auto-generated from docstrings)
- [ ] Add section for require_user_auth parameter
- [ ] Add section for event._user_token attribute
- [ ] Add section for TokenRefreshError exception
- [ ] Verify all public APIs documented with Google-style docstrings
- [ ] Verify docs render correctly: `uv run mkdocs serve`
- [ ] Check for broken links

---

### Task 4.9: Final integration testing
**Deliverable:** Complete test suite passing

**Acceptance Criteria:**
- [ ] Run all tests: `uv run pytest`
- [ ] All tests pass (100%)
- [ ] Run type checking: `uv run pyrefly`
- [ ] No type errors
- [ ] Run linting: `uv run ruff check`
- [ ] No linting errors
- [ ] Run formatting check: `uv run ruff format --check`
- [ ] No formatting issues
- [ ] Check coverage: `uv run pytest --cov=src/frameio_kit --cov-report=term-missing`
- [ ] Verify ≥95% coverage for new code
- [ ] Fix any issues discovered
- [ ] Re-run all checks until passing

---

### Task 4.10: Update README and changelog
**Deliverable:** Updated `README.md` and `CHANGELOG.md`

**Acceptance Criteria:**
- [ ] Add OAuth feature to README.md "Why frameio-kit?" section
  - "User authentication via Adobe Login OAuth"
- [ ] Add link to user authentication docs in README
- [ ] Create CHANGELOG.md if doesn't exist
- [ ] Add entry for new version (e.g., v0.1.0):
  - Date
  - "Added" section with OAuth feature
  - Link to user authentication docs
  - Link to GitHub issue #31
- [ ] Add migration notes if needed (none for this - fully backward compatible)
- [ ] Verify markdown renders correctly on GitHub

---

## Execution Guidelines

### Before Starting Each Task:
1. Read the task description and acceptance criteria
2. Ensure previous dependent tasks are complete
3. Create a todo list for the task if complex

### While Working on Task:
1. Write code following AGENT.md principles
2. Add comprehensive docstrings (Google-style)
3. Include full type hints
4. Write tests as you go (TDD when possible)

### After Completing Each Task:
1. Verify all acceptance criteria met
2. Run relevant tests: `pytest path/to/test_file.py`
3. Run type checking: `pyrefly`
4. Run linting: `ruff check` and `ruff format`
5. Commit changes with clear message
6. Mark task as complete

### Dependencies:
- **Phase 1 → Phase 2**: Must complete all Phase 1 tasks before starting Phase 2
- **Phase 2 → Phase 3**: Must complete all Phase 2 tasks before starting Phase 3
- **Phase 3 → Phase 4**: Can overlap - documentation/examples can start during Phase 3

### Estimated Timeline:
- **Phase 1**: 1-2 weeks (6 tasks)
- **Phase 2**: 2 weeks (9 tasks)
- **Phase 3**: 2 weeks (9 tasks)
- **Phase 4**: 1-2 weeks (10 tasks, some parallel)
- **Total**: 6-8 weeks for complete implementation

---

## Success Metrics

### Technical:
- [ ] All 28 tasks completed
- [ ] 100% test pass rate
- [ ] ≥95% code coverage for new code
- [ ] Zero type errors (pyrefly strict mode)
- [ ] Zero linting errors (ruff)
- [ ] Zero breaking changes to existing API

### Documentation:
- [ ] All new features documented
- [ ] All examples working
- [ ] Migration guide complete (if needed)
- [ ] API reference up-to-date

### Quality:
- [ ] Security audit passed
- [ ] Performance benchmarks met (<10ms MemoryStore, <50ms Redis)
- [ ] Production examples deployable
- [ ] Community feedback positive (after release)

---

**Ready to execute!** Start with Task 1.1 and work sequentially through each phase.
