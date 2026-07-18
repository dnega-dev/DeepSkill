---
repo: fastapi/fastapi
deepwiki: https://deepwiki.com/fastapi/fastapi
github: https://github.com/fastapi/fastapi
harvested: 2026-07-09
cluster: backend-and-deployment
---

> Distilled from the DeepWiki wiki for [`fastapi/fastapi`](https://deepwiki.com/fastapi/fastapi) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# FastAPI — Distilled Knowledge

## What it is

FastAPI is a Python web framework for building HTTP APIs, built on two foundational libraries: **Starlette** (ASGI framework — routing, middleware, WebSocket, ASGI lifecycle) and **Pydantic** (data validation, serialization, JSON Schema generation). FastAPI itself is an orchestration layer that connects standard Python type hints to automatic request validation, response serialization, and OpenAPI documentation generation. Its central design principle is "declare once, get everything": a single function signature with type annotations simultaneously defines where parameters come from (path/query/header/cookie/body), what validation applies, the response schema, the OpenAPI doc, and editor autocompletion.

Runtime dependencies are exactly two packages: `starlette` and `pydantic`. The `fastapi[standard]` install extra adds `uvicorn` (server), `fastapi-cli` (dev tooling), and `httpx` (testing).

## Architecture (how it's built, key components)

Layered stack (top to bottom): ASGI server (Uvicorn) → Starlette (ASGI framework, middleware stack) → `AsyncExitStackMiddleware` → `FastAPI` application (extends `starlette.Starlette`) → `APIRouter` → `APIRoute` → request handler (`get_request_handler()` in `fastapi/routing.py`) → dependency resolution (`solve_dependencies()`) → path operation function → response serialization.

Core abstractions:
- **`Dependant`** (`fastapi/dependencies/models.py`): a dataclass representing one node of the dependency tree — holds `path_params`, `query_params`, `header_params`, `cookie_params`, `body_params` (all lists of `ModelField`), the `call` (actual callable), a list of sub-`dependencies` (recursive), `scope` (`"function"` or `"request"`), and special-parameter slots for `Request`, `WebSocket`, `Response`, `BackgroundTasks`, `SecurityScopes`. Built once at route-registration time by `get_dependant()`, which uses `inspect.signature` to walk the function signature (`analyze_param()` classifies each parameter).
- **`ModelField`** (`fastapi/_compat` / `fastapi/utils.py::create_model_field()`): FastAPI's bridge to Pydantic v2's `TypeAdapter`/`CoreSchema`. Exposes `.validate()` (returns `(value, errors)`) and `.serialize()`. The same `ModelField` instances used for runtime validation are reused for OpenAPI schema generation, so docs and runtime behavior cannot drift apart.
- **`APIRoute`** (`fastapi/routing.py`): built at decoration time (`@app.get(...)`); computes `self.dependant` (via `get_dependant()`), `self._flat_dependant` (flattened for parameter extraction), `self.body_field` (combined Pydantic model for all body params), and `self.response_field`.
- **`_compat` layer** (`fastapi/_compat/{shared,v2}.py`): historically abstracted Pydantic v1 vs v2 differences; as of the v1-removal (FastAPI 0.128.0) it's simplified to just wrap Pydantic v2 internals (`v2.ModelField`, `v2.serialize_sequence_value()`).

AsyncExitStack resource management: FastAPI stores two nested `contextlib.AsyncExitStack` instances in `request.scope` per request — `fastapi_inner_astack` (request-scoped dependency cleanup) and `fastapi_function_astack` (function-scoped cleanup) — plus a middleware-level stack for cleaning up temporary upload files. These let dependencies declared with `yield` run their teardown code even if an exception is raised mid-request.

## Key patterns & techniques (the transferable knowledge)

**Dependency injection (`Depends`/`Security`)**
- `Depends(callable)` marks a parameter as an injectable dependency; `Depends()` with no argument uses the parameter's own type annotation as the callable.
- Resolution is recursive: `solve_dependencies()` walks `dependant.dependencies` depth-first, resolves each sub-dependency (checking `dependency_overrides_provider` for test overrides first), executes the callable (as coroutine or via threadpool if sync), and stores the result keyed by name.
- **Caching by default**: each `Dependant` computes a cache key from `(call, sorted(set(oauth_scopes)), computed_scope)`. If `use_cache=True` (default) and the key is already in the per-request `dependency_cache` dict, the cached value is reused instead of re-executing — this means an expensive dependency shared by multiple other dependencies in the same request only runs once. Pass `use_cache=False` to force re-execution.
- **Dependencies with `yield`** act as context managers: sync generators are wrapped via `contextmanager_in_threadpool`, async generators via `asynccontextmanager`, and entered onto the appropriate `AsyncExitStack`. This is the idiomatic way to hand out a DB session/connection and guarantee cleanup (`try/finally`-equivalent) regardless of success or exception.
- Special types (`Request`, `WebSocket`, `HTTPConnection`, `Response`, `BackgroundTasks`, `SecurityScopes`) are auto-injected by type annotation alone — no `Depends()` needed.
- Dependencies declared in a route/router's `dependencies=[...]` list run but their return value is discarded — useful for auth/rate-limit checks that don't need to feed a value into the handler.

**Security schemes as dependencies**
- All security classes (`OAuth2PasswordBearer`, `HTTPBasic`, `HTTPBearer`, `HTTPDigest`, `APIKeyQuery/Header/Cookie`, `OpenIdConnect`) inherit from `SecurityBase` and are themselves callables usable with `Depends()`/`Security()` — they extract credentials from the request and either return them or raise 401/403.
- `Security(dependency, scopes=[...])` (instead of `Depends`) attaches OAuth2 scope requirements. Scopes accumulate through the dependency tree (`own_oauth_scopes` merged with `parent_oauth_scopes`) and surface both at runtime (inject a `SecurityScopes` parameter to compare required vs. granted) and in the generated OpenAPI security requirements.
- JWT auth is NOT built into FastAPI — the documented pattern combines `OAuth2PasswordRequestForm` (extracts `username`/`password` from form data) + `PyJWT` (`jwt.encode`/`jwt.decode`) + `pwdlib` (bcrypt/argon2 password hashing) assembled by the application. `OAuth2PasswordBearer.__call__()` just extracts the raw bearer token string from the `Authorization` header; token verification is entirely user code.

**Validation & error handling**
- Exception hierarchy: `starlette.HTTPException` → `fastapi.HTTPException` (client errors, carries `status_code`/`detail`/`headers`); a separate `ValidationException` base (not HTTPException-derived) covers `RequestValidationError` (request param/body failures, carries raw `body`), `WebSocketRequestValidationError`, and `ResponseValidationError` (response failed to match `response_model`, also carries `body`).
- Validation errors are auto-enriched with **endpoint context** (source file, line number, function name, HTTP method+path) via `_extract_endpoint_context()`, cached per-function-object to avoid repeated `inspect` I/O on every failing request — worth stealing this caching pattern for any framework that inspects call sites frequently.
- Response validation is a genuine **security control**: FastAPI clones the response-model `ModelField` (`create_cloned_field()`) specifically to stop a subclass with extra sensitive fields (e.g., `UserInDB` with `hashed_password`) from leaking those fields just because it's-a instance of the public `User` model. Always define a narrower response model rather than reusing your DB/internal model.

**Response serialization**
- Response-class resolution priority is route-level `response_class` → router-level `default_response_class` → app-level `default_response_class`, implemented via a `DefaultPlaceholder` sentinel so "not explicitly set" is distinguishable from "explicitly set to the default."
- `serialize_response()` fast-paths straight to Pydantic v2's Rust serializer (`field.serialize()`) when a `response_field` exists; falls back to the slower universal `jsonable_encoder()` (handles dataclasses, `datetime`, `Enum`, custom encoders, etc.) when there's no response model or for edge cases.
- Granular response shaping knobs: `response_model_include/exclude`, `response_model_by_alias`, `response_model_exclude_unset/defaults/none` — all flow through to the serializer per-route.

**Routing & composition**
- `APIRouter(prefix=..., tags=..., dependencies=...)` groups routes and can be nested; `include_router()` merges prefixes, tags, and dependencies from parent into child. As of FastAPI 0.137.0, `include_router()` preserves the original `APIRouter`/`APIRoute` instances rather than cloning them (a notable behavior change from earlier versions).
- Path compilation reuses Starlette's `compile_path()` to turn `"/items/{item_id}"` into a matching regex at route-registration time, not per-request.
- Sub-application lifespans can be merged: `_merge_lifespan_context()` lets a sub-router's own startup/shutdown logic nest inside the parent app's lifespan.
- Dependency analysis (`get_dependant()`) happens once at route-registration time, not per-request — only *resolution* (`solve_dependencies()`) happens per-request. This is a good general pattern: do signature/schema introspection at build time, keep the request-time path to pure execution.

**WebSocket support**
- `@app.websocket(path)` builds an `APIWebSocketRoute`, which runs the *same* `get_dependant()`/`solve_dependencies()` machinery as HTTP routes — WS endpoints can declare `Depends`, path/query/header/cookie params exactly like HTTP handlers.
- Connection flow: ASGI server → `websocket_session()` wraps the raw `WebSocket` object and sets up the two `AsyncExitStack`s → `get_websocket_app()` calls `solve_dependencies()` → on validation failure raises `WebSocketRequestValidationError`; otherwise calls the endpoint with `**solved_values`.

**OpenAPI generation**
- `FastAPI.openapi()` calls `get_openapi()` (in `fastapi/openapi/utils.py`) once, then caches the resulting dict in `self.openapi_schema`; subsequent requests to `/openapi.json` are served from cache (invalidate manually if you mutate routes after startup).
- Operation IDs default to `{route.name}{route.path_format}` sanitized and suffixed with `_{method}`; pass `generate_unique_id_function` to `FastAPI`/`APIRouter` for clean, stable IDs — recommended when generating SDKs from the schema, since default IDs are verbose.
- `include_in_schema=False` on `Query`/`Header`/`Cookie`/`Path`/route decorators hides a parameter or whole route from the generated schema while keeping it fully functional at runtime — useful for internal/debug endpoints.
- Two validation-error schemas (`ValidationError`, `HTTPValidationError`) are hardcoded and auto-added to `components.schemas`.
- Additional documented responses use `responses={404: {"model": ErrorModel, "description": "..."}}` on the route decorator, deep-merged into the generated `responses` object.

## Practical how-tos

- **Minimal app**: `from fastapi import FastAPI; app = FastAPI()` then decorate functions with `@app.get("/path")`; run with `fastapi dev main.py` (provided by `fastapi-cli`, auto-detects the `FastAPI` instance, hot-reloads).
- **DB session per request with cleanup**: write `def get_db(): db = SessionLocal(); try: yield db; finally: db.close()`, then use `db: Session = Depends(get_db)` in handlers — FastAPI's `AsyncExitStack` guarantees `finally` runs even on exceptions.
- **Group and scope OAuth2 permissions**: `Security(get_current_user, scopes=["items:read"])` on handlers; inject `security_scopes: SecurityScopes` in the dependency to check `security_scopes.scopes` against the decoded token's granted scopes and raise 403 if insufficient.
- **Prevent sensitive-field leakage in responses**: define separate `UserOut`/`UserInDB` Pydantic models; set `response_model=UserOut` on the route rather than returning the DB model directly — FastAPI's field cloning enforces the narrower schema even if you accidentally return the fuller object.
- **Testing with dependency overrides**: `app.dependency_overrides[get_db] = override_get_db` — `solve_dependencies()` checks `dependency_overrides_provider` before falling back to the real dependency, so tests can swap in fakes without touching route code.
- **Organize a larger app**: split path operations into multiple `APIRouter()` instances per resource/module, then `app.include_router(users_router, prefix="/users", tags=["users"])` in the main app file.

## Gotchas & caveats

- Pydantic v1 support was fully removed as of FastAPI 0.128.0 (deprecated in 0.126.0, warned in 0.127.0). Minimum supported Pydantic is `>=2.7.0`. Any code still importing `pydantic.v1` will break.
- Python 3.8 support dropped at 0.125.0; Python 3.9 dropped at 0.129.0 — check your runtime before upgrading FastAPI.
- `ORJSONResponse`/`UJSONResponse` were deprecated in 0.131.0; `fastapi-slim` package was dropped in 0.129.2.
- As of 0.132.0, FastAPI performs **strict Content-Type checking** for JSON bodies — this is a request-validation behavior change that can break clients sending JSON without an exact `application/json` (or `*+json`) content type.
- `WSGIMiddleware` was moved out of FastAPI into the separate `a2wsgi` package — code relying on the old import path needs updating.
- `include_router()`'s behavior changed at 0.137.0 to preserve rather than clone `APIRouter`/`APIRoute` instances — if you relied on router cloning semantics (e.g., mutating a router after inclusion expecting the included copy to be unaffected), this is a breaking change.
- Duplicate `operation_id`s in the generated OpenAPI schema only emit a `warnings.warn()`, not an exception — don't assume the schema is valid just because the app started without errors.
- Response validation errors and request validation errors are structurally similar (`ValidationException` subclasses) but conceptually different: a `ResponseValidationError` means *your own handler's return value* didn't match its declared `response_model` — a server-side bug, not a client error, and should generally not be exposed verbatim to callers.

## Wiki pages used

- FastAPI Overview
- Core Framework Architecture
- Application and Routing System
- Dependency Injection System
- Request Processing Pipeline
- Response Handling and Serialization
- OpenAPI Schema Generation (partial)
- Security and Authentication
- Error Handling and Validation
- WebSocket Support (partial)
- Breaking Changes and Migration
