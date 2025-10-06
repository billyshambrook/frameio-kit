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
| **Type Checking** | **pyrefly** | Configure in pyproject.toml. |
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
