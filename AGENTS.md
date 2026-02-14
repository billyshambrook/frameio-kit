# **AGENT.md: Engineering & AI Contributor Guide**

## **🎯 Mission Statement**

Our goal is to build and maintain a best-in-class, modern Python SDK for the Frame.io API. This library should be a pleasure to use, characterized by its explicitness, robust type safety, asynchronous-first design, and excellent performance. This guide outlines the principles and technical standards that all contributors—both human and AI—must adhere to.

## **🏗️ Core Architectural Principles**

1. **Asynchronous First**: All operations involving I/O (i.e., network requests to the Frame.io API) **MUST** be implemented using async/await. This ensures the library is non-blocking and suitable for high-performance applications.  
2. **Explicitness & Type Safety**: The library must be fully type-hinted. We aim for 100% static analysis pass rates with mypy in its strictest configuration. This eliminates ambiguity and reduces runtime errors.  
3. **Developer Experience (DX) is Paramount**: The API client should be intuitive. It should mirror the structure of the Frame.io REST API. For example, interacting with files should feel natural: await client.files.get("file\_id\_...").  
4. **Minimal Dependencies**: Only include dependencies that are essential and well-maintained. We prefer single-purpose, high-performance tools over large, monolithic frameworks.  
5. **Robust Error Handling**: The library must define a clear hierarchy of custom exceptions (e.g., FrameIOApiException, AuthenticationError, SignatureVerificationError) to allow developers to handle specific failure modes gracefully. Do not raise generic Exception.

## **🛠️ Technology Stack & Tooling**

Adherence to this stack is mandatory. Do not introduce new tools without a formal decision-making process.

| Category | Tool | Configuration & Notes |
| :---- | :---- | :---- |
| **Python Version** | **3.13+** | Utilize modern language features such as the \` |
| **Dependency Mgmt** | **uv** | Use uv pip compile and uv pip sync for fast, deterministic dependency resolution. All dependencies must be defined in pyproject.toml. Do not use requirements.txt for the library itself. |
| **Linting & Formatting** | **Ruff** | A single, high-performance tool for both linting and formatting. Configure ruff.toml to enforce strict rules, including isort for import sorting. The code base must be 100% compliant with ruff check and ruff format. |
| **Type Checking** | **basedpyright** | Configure in pyproject.toml under `[tool.basedpyright]`. |
| **Testing** | **pytest** & **pytest-asyncio** | All tests must be written using pytest. Asynchronous code must be tested using pytest-asyncio. |
| **HTTP Client** | **httpx** | Use httpx.AsyncClient for all API calls. Leverage its features for connection pooling, timeouts, and handling async requests. For tests, use httpx.MockRouter to mock API responses reliably without actual network calls. |
| **Data Modeling** | **Pydantic** | All API response models and request bodies **MUST** be defined as Pydantic models. This provides data validation, serialization, and excellent editor support out-of-the-box. |
| **Web Framework (App)** | **Starlette** (or FastAPI) | The ASGI application (FrameApp) should be built on the minimal, high-performance Starlette toolkit. FastAPI is acceptable if more advanced features like dependency injection are required, but Starlette is preferred for simplicity. |
| **Documentation** | **MkDocs** with **pydoc** | Generate beautiful, modern documentation directly from your code's docstrings. All public functions, classes, and methods must have comprehensive docstrings in the **Google Style**. |
| **CI/CD** | **GitHub Actions** | The .github/workflows/ directory should contain workflows that automatically run ruff, mypy, and pytest on every pull request. |
| **Security** | **Environment Variables** with **pydantic-settings** | Never hardcode secrets. API tokens, webhook secrets, etc., should be loaded from environment variables. pydantic-settings is the preferred way to manage this configuration. |

## **🧪 Testing Strategy**

- Test the public API's behavior, not private implementation details. This approach supports safe refactoring, as internal code can change without breaking tests.
- Verify all logical paths and error conditions. Test the happy path, edge cases, and assert that exceptions are handled or raised correctly using pytest.raises.
- Isolate units by mocking external dependencies like networks or databases. This ensures that your unit tests are fast, deterministic, and reliable.
- Use code coverage as a guide to find untested code. Balance your test suite with many fast unit tests and fewer, targeted integration tests, following the Test Pyramid principle.

## **✍️ Code Contribution Workflow & Guidelines**

1. **Docstrings (Google Style)**: Every public class, method, and function must have a docstring.  
   async def get\_file(self, file\_id: str) \-\> File:  
       """Retrieves a specific file by its unique ID.

       This function makes an asynchronous call to the \`GET /files/{file\_id}\` endpoint.

       Args:  
           file\_id: The unique identifier for the file.

       Returns:  
           A Pydantic model of the requested File.

       Raises:  
           FrameIOApiException: If the API returns a non-2xx status code.  
       """  
       response \= await self.http.get(f"files/{file\_id}")  
       response.raise\_for\_status() \# Let httpx handle raising exceptions for bad statuses  
       return File(\*\*response.json())

2. **API Client Structure**: The client should be organized by API resources.  
   \# Good: Intuitive and mirrors the REST API  
   class FrameioClient:  
       def \_\_init\_\_(self, token: str):  
           self.files \= FilesClient(...)  
           self.comments \= CommentsClient(...)

   \# Bad: A flat client with no organization  
   class FrameioClient:  
       async def get\_file(...) \-\> ...: ...  
       async def create\_comment(...) \-\> ...: ...

3. **Testing**:  
   * Create a tests/ directory.  
   * For every new feature, add corresponding tests.  
   * For every bug fix, add a regression test that fails before the fix and passes after.  
   * Use pytest.mark.asyncio for all async test functions.  
4. **Commits**: Write clear, concise commit messages that explain the *why* behind a change, not just the *what*.  
5. **Pull Requests**:
   * A PR should address a single, focused issue.
   * The description should clearly explain the changes and link to any relevant issue trackers.
   * Ensure all CI checks (linting, type checking, testing) are passing before requesting a review.

## **🏛️ Module Architecture**

The SDK follows a modular architecture with clear separation of concerns:

| Module | Purpose |
|--------|---------|
| `_app.py` | Main application class (orchestration only) |
| `_exceptions.py` | Custom exception hierarchy |
| `_secret_resolver.py` | Secret resolution strategy |
| `_oauth_manager.py` | OAuth component lifecycle |
| `_request_handler.py` | Request parsing, validation, verification |
| `_events.py` | Event models (WebhookEvent, ActionEvent) |
| `_responses.py` | UI response models (Message, Form, fields) |
| `_middleware.py` | Middleware base class |
| `_security.py` | Signature verification |
| `_oauth.py` | OAuth client and token management |
| `_encryption.py` | Token encryption |
| `_client.py` | Frame.io API client |
| `_context.py` | Request context management |
| `_auth_routes.py` | OAuth authentication routes |
| `_auth_templates.py` | Auth callback page templates |
| `_storage.py` | Storage abstraction (MemoryStorage) |
| `_storage_dynamodb.py` | DynamoDB storage backend |
| `_install_models.py` | Installation data models |
| `_install_manager.py` | Installation lifecycle management |
| `_install_routes.py` | Install UI route handlers (HTMX) |
| `_install_templates.py` | Install UI Jinja2 templates |
| `_install_secret_resolver.py` | Auto-wired secret resolver for installations |

### Design Principles

1. **Single Responsibility**: Each module should have one clear purpose
2. **Extract, Don't Expand**: When a class grows too large, extract focused classes
3. **Use Custom Exceptions**: Prefer specific exception types over generic ones
4. **Fail Fast**: Validate at startup when possible, not at request time

## **⚠️ Common Pitfalls to Avoid**

### Never Use Mutable Default Arguments
```python
# Bad
def __init__(self, middleware: list[Middleware] = []):
    self._middleware = middleware

# Good
def __init__(self, middleware: list[Middleware] | None = None):
    self._middleware = middleware or []
```

### Never Use `assert` in Production Code
```python
# Bad
assert self._config is not None, "Config required"

# Good
if self._config is None:
    raise RuntimeError("Config required")
```

### Use TypedDict for Structured Dictionaries
```python
# Bad
state_data: dict[str, Any] = {"user_id": user_id}

# Good
class OAuthStateData(TypedDict):
    user_id: str
    interaction_id: str | None
    redirect_url: str

state_data: OAuthStateData = {"user_id": user_id, ...}
```

### Never Expose Exception Details to Users
```python
# Bad
except Exception as e:
    return Response(f"Error: {str(e)}", status_code=500)

# Good
except Exception:
    logger.exception("OAuth token exchange failed")
    return Response("An error occurred", status_code=500)
```

### Handle Each Resource Cleanup Independently
```python
# Bad - if first fails, second never runs
if self._api_client:
    await self._api_client.close()
if self._oauth_manager:
    await self._oauth_manager.close()

# Good - both always attempted
cleanup_errors = []
for client in [self._api_client, self._oauth_manager]:
    if client:
        try:
            await client.close()
        except Exception as e:
            logger.exception("Error closing client")
            cleanup_errors.append(e)
```

### Validate Timestamps in Both Directions
```python
# Bad - only checks past
if (current_time - timestamp) > TOLERANCE:
    return False

# Good - checks past and future
time_diff = current_time - timestamp
if abs(time_diff) > TOLERANCE:
    return False
```

### Use Logger, Not Warnings
```python
# Bad
import warnings
warnings.warn("Using ephemeral key", UserWarning)

# Good
import logging
logger = logging.getLogger(__name__)
logger.warning("Using ephemeral key - tokens will be lost on restart")
```

### Keep Imports at Top of File
Move imports to the top unless there's a specific reason (circular imports, conditional dependencies).

## **🔐 Exception Hierarchy**

```
FrameioKitError (base)
├── SecretResolutionError
├── SignatureVerificationError
├── EventValidationError
├── ConfigurationError
├── InstallationError
│   └── InstallationNotFoundError
└── OAuthError
    ├── TokenExchangeError
    └── TokenRefreshError
```

All public exceptions should be exported from `__init__.py` to allow users to handle specific error cases.
