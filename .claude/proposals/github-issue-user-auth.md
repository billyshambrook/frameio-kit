# GitHub Issue: Add Adobe Login OAuth User Authentication Support

**Copy this content when creating the GitHub issue**

---

## Title
Add Adobe Login OAuth User Authentication for Custom Actions

## Labels
`enhancement`, `feature-request`, `user-authentication`, `oauth`

## Description

### Problem Statement

Currently, frameio-kit requires developers to use server-to-server (S2S) application tokens for all API calls. This means:

- **No user attribution**: API calls appear to come from the application, not the user who triggered the action
- **Lost audit trails**: Frame.io activity logs don't show which user actually performed actions through the integration
- **Permission misalignment**: The S2S token may have different permissions than the user
- **Poor user experience**: Users can't leverage their own Frame.io permissions and identity

### Proposed Solution

Add support for **Adobe Login OAuth 2.0** to enable custom actions to execute with user-specific tokens. This would allow:

- ✅ Actions to execute in the user's context with proper attribution
- ✅ API calls to appear as the actual user in Frame.io activity logs
- ✅ Seamless authentication flow that persists tokens across actions
- ✅ Automatic token refresh to maintain user sessions
- ✅ Opt-in per action design with zero breaking changes

### User Story

**As a** frameio-kit developer,
**I want** my custom actions to execute with the user's identity,
**So that** API calls are properly attributed and users maintain their Frame.io permissions context.

### Example Usage

```python
from frameio_kit import App, ActionEvent, OAuthConfig, Message

# Configure OAuth at app level
app = App(
    token=os.getenv("FRAMEIO_TOKEN"),  # Still available for non-auth actions
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri=os.getenv("ADOBE_REDIRECT_URI"),
    )
)

# Opt-in to user authentication per action
@app.on_action(
    "my_app.share_file",
    name="Share with Team",
    description="Share this file with your team",
    secret=os.getenv("ACTION_SECRET"),
    require_user_auth=True,  # 🆕 New parameter
)
async def share_file(event: ActionEvent):
    # This now executes with the user's token
    # Appears in Frame.io logs as the actual user, not the app
    file = await app.client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )

    # ... sharing logic ...

    return Message(title="Shared!", description="File shared successfully!")
```

### Key Features

#### 1. **Opt-In Design**
- Actions explicitly opt into user authentication via `require_user_auth=True`
- Existing actions continue to use S2S tokens without any changes
- Zero breaking changes to the current API

#### 2. **Seamless Authentication Flow**
- User triggers action requiring auth → Framework automatically presents Adobe Login
- After authentication, tokens are stored and reused for future actions
- Built-in OAuth endpoints (`/.auth/login`, `/.auth/callback`) automatically mounted

#### 3. **Token Management**
- Automatic token refresh before expiration
- Secure encryption at rest using Fernet (cryptography library)
- Tokens keyed by `user_id` from ActionEvent for proper isolation

#### 4. **Flexible Storage Backends**
- **MemoryStore** (default): Simple, no external dependencies
- **DiskStore**: Single-server persistent storage
- **RedisStore** (optional): Multi-server distributed deployments
- Inspired by FastMCP's storage layer design with pluggable backends

#### 5. **Production-Ready Security**
- Fernet symmetric encryption for tokens at rest
- CSRF protection via state tokens
- HTTPS enforcement in production
- Configurable encryption keys via environment variables
- Automatic token expiration and refresh

### Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     frameio-kit App                          │
│                                                               │
│  OAuth Config → Auth Middleware → Token Manager              │
│                       ↓                  ↓                    │
│                  ActionEvent        Storage Backend           │
│                       ↓              (Memory/Disk/Redis)      │
│                 User Token                                    │
│                  Injection                                    │
│                       ↓                                       │
│               Frame.io API Client                             │
└───────────────────────────────────────────────────────────────┘
```

### Requirements

#### Functional Requirements
- [ ] Adobe IMS OAuth 2.0 integration
- [ ] Token storage abstraction layer (Memory, Disk, Redis)
- [ ] Automatic token refresh mechanism
- [ ] Secure token encryption at rest (Fernet)
- [ ] Built-in OAuth endpoints (only mounted when auth enabled)
- [ ] Middleware for automatic token injection
- [ ] Graceful handling of unauthenticated users (return Form with login link)
- [ ] Token reuse across multiple actions for same user

#### Non-Functional Requirements
- [ ] Zero breaking changes to existing API
- [ ] <10ms latency overhead for in-memory storage
- [ ] <50ms latency overhead for Redis storage
- [ ] 100% type hints compatible with strict type checking
- [ ] Full async/await implementation
- [ ] Comprehensive documentation and examples

#### Developer Experience
- [ ] Simple app-level configuration
- [ ] Clear error messages and debugging guidance
- [ ] Example applications for common use cases
- [ ] Migration guide from S2S-only usage
- [ ] Security best practices documentation

### Implementation Phases

**Phase 1: Foundation** (Weeks 1-2)
- Storage abstraction interface
- MemoryStore and DiskStore implementations
- Token encryption using Fernet
- Unit tests and documentation

**Phase 2: OAuth Integration** (Weeks 3-4)
- Adobe IMS OAuth client
- Token manager with refresh logic
- OAuth endpoints (login/callback)
- Integration tests with mocked Adobe IMS

**Phase 3: Middleware Integration** (Weeks 5-6)
- Auth middleware for token injection
- App configuration updates
- Graceful authentication flow (Form with login link)
- End-to-end tests

**Phase 4: Production Features** (Weeks 7-8)
- RedisStore implementation
- Key rotation utilities
- Performance optimization
- Security audit
- Complete documentation

### Success Criteria

- ✅ Zero breaking changes to existing frameio-kit API
- ✅ OAuth setup completable in <15 minutes with documentation
- ✅ Passes comprehensive security audit
- ✅ 100% test coverage for authentication components
- ✅ Positive feedback from beta testers
- ✅ Production-ready with multiple storage backends

### Dependencies

**New Required:**
- `cryptography>=44.0.0` - Fernet encryption (~3MB)

**New Optional:**
- `redis[asyncio]>=5.2.0` - For RedisStore backend
- `keyring>=25.6.0` - System keyring for dev key management
- `aiofiles>=24.1.0` - Async file I/O for DiskStore

### Related Documentation

📄 **[Full Technical Proposal](.claude/proposals/adobe-oauth-user-auth.md)** - Comprehensive design document with:
- Detailed architecture and component designs
- Complete API specifications
- Security considerations and best practices
- Code examples and usage patterns
- Testing strategy
- Migration path

### Questions for Discussion

1. Should we support token introspection APIs for debugging?
2. What should the default token TTL be before requiring re-authentication?
3. Should we provide admin APIs for bulk token revocation?
4. Should we support multiple Adobe IMS environments (stage, production)?

### Prior Art

This design is inspired by:
- [FastMCP](https://gofastmcp.com) - Storage backend abstraction and token encryption patterns
- [py-key-value-aio](https://github.com/strawgate/py-key-value) - Async key-value storage interface
- OAuth 2.0 Best Practices (RFC 6749, RFC 6819)

---

**We welcome feedback and contributions!** Please comment with:
- Use cases this would enable for you
- Concerns about the proposed approach
- Additional features or storage backends you'd like to see
- Questions about implementation details

cc @billyshambrook
