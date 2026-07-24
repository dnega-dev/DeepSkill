---
repo: pydantic/pydantic
deepwiki: https://deepwiki.com/pydantic/pydantic
github: https://github.com/pydantic/pydantic
harvested: 2026-07-09
cluster: backend-and-deployment
---

> Distilled from the DeepWiki wiki for [`pydantic/pydantic`](https://deepwiki.com/pydantic/pydantic) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# Pydantic — Distilled Knowledge

## What it is

Pydantic is a Python data validation library that uses type hints to validate and serialize data — described in its own docs as "the most widely used data validation library for Python." Its core purpose is transforming unvalidated input data into validated Python objects using type annotations, while also providing serialization and JSON Schema generation. Requires Python 3.10+. As of v2.13.0, the `pydantic-core` (Rust) repository was merged into the main `pydantic` monorepo. Current version at time of writing: Pydantic 2.13.0, requiring pydantic-core 2.46.0 (version compatibility is checked at runtime).

Pydantic V2 has two validation modes: **strict** (no type coercion) and **lax** (coerces compatible types, e.g. `'123'` → `123` for an `int` field).

## Architecture (how it's built, key components)

**The Python/Rust split**: Pydantic V2 splits into two parts. The `pydantic` Python package handles high-level logic — schema generation (translating Python type annotations into a `CoreSchema` dict), configuration, and the public API surface. The `pydantic-core` Rust package (built with `pyo3`) contains the actual validation and serialization engine: it compiles a `CoreSchema` dict into a `SchemaValidator` (a tree of Rust structs implementing a `Validator` trait) and a `SchemaSerializer`. This is the reason for pydantic v2's large performance jump over v1 — the hot validation/serialization path runs in compiled Rust, not interpreted Python.

Three-phase pipeline: (1) **Schema Generation** (Python) — `GenerateSchema` (`pydantic/_internal/_generate_schema.py`) walks `__annotations__` and `FieldInfo` objects to build a `CoreSchema` dict; (2) **Compilation** (Rust) — the `CoreSchema` dict is handed to `pydantic-core`, which builds a `SchemaValidator` and `SchemaSerializer` by recursively calling `build_validator()` per schema node (e.g. a `{"type": "union", "choices": [...]}` dict becomes a Rust `UnionValidator`); (3) **Execution** — `SchemaValidator.validate_python()` / `validate_json()` process real input data and return either a validated object or raise `ValidationError`.

**Model construction (`ModelMetaclass`)**: When a class inherits `BaseModel`, `ModelMetaclass.__new__` (in `pydantic/_internal/_model_construction.py`) intercepts creation and orchestrates: `_collect_bases_data()` gathers parent-class fields → `inspect_namespace()` identifies field annotations vs. private attributes → `collect_model_fields()` builds `__pydantic_fields__: dict[str, FieldInfo]` → `complete_model_class()` generates the `CoreSchema` → `create_schema_validator()` builds the compiled `SchemaValidator` and a `SchemaSerializer`. This all happens once at class-definition time, not per-instance.

Key instance/class attributes set by the metaclass: `__pydantic_validator__` (compiled `SchemaValidator`), `__pydantic_serializer__` (compiled `SchemaSerializer`), `__pydantic_core_schema__` (the `CoreSchema` dict), `__pydantic_fields__`, `__pydantic_fields_set__` (which fields were explicitly passed at init), `__pydantic_extra__` (extra fields if `extra='allow'`), `__pydantic_private__` (private attribute storage), `__pydantic_computed_fields__`.

**Decorator collection system**: `@field_validator`, `@model_validator`, `@field_serializer`, `@model_serializer`, and `@computed_field` all wrap their target function in a `PydanticDescriptorProxy`, discoverable by the metaclass when scanning class attributes. All discovered decorators are aggregated into a single `DecoratorInfos` dataclass (fields: `validators`, `field_validators`, `root_validators`, `model_validators`, `field_serializers`, `model_serializers`, `computed_fields`) attached as `__pydantic_decorators__`. Schema generation reads this container to splice validator/serializer functions into the `CoreSchema` at the right nodes.

**Configuration (`ConfigDict`/`ConfigWrapper`)**: `ConfigDict` is a `TypedDict` covering four option categories — validation (`strict`, `validate_assignment`, `validate_default`, `extra`), serialization (`use_enum_values`, `ser_json_timedelta`), behavior (`frozen`, `protected_namespaces`, `arbitrary_types_allowed`), and generators (`alias_generator`, `field_title_generator`). Set via `model_config = ConfigDict(...)` class attribute. Internally, `ConfigWrapper` converts the raw dict into an object with slotted attributes for fast access during schema generation. Inheritance order (lowest to highest priority): library defaults → base classes in MRO order → the class's own `model_config`/legacy `Config` class → keyword arguments on the class definition itself (e.g. `class M(BaseModel, frozen=True)`).

## Key patterns & techniques (the transferable knowledge)

**Validator execution order** (a general pattern worth internalizing for any layered-validation system): for a given field, validators run in this sequence: (1) `BeforeValidator` from `Annotated` metadata, (2) `@field_validator(mode='before')`, (3) standard type validation/coercion (e.g. str→int), (4) `@field_validator(mode='after')`, (5) `AfterValidator` from `Annotated` metadata. Four validator modes exist: `before` (runs pre-type-check), `after` (post-type-check), `plain` (replaces type-check entirely), `wrap` (wraps type-check, receives a handler to invoke the next layer — the middleware pattern applied to per-field validation). Model-level `@model_validator(mode='before')` receives the raw input dict; `mode='after'` receives the already-instantiated model.

**Functional validators/serializers via `Annotated`**: `AfterValidator`, `BeforeValidator`, `PlainValidator`, `WrapValidator` (and their serializer counterparts `PlainSerializer`, `WrapSerializer`) are ordinary Python objects placed inside `Annotated[T, ...]` that implement `__get_pydantic_core_schema__(source_type, handler)` — calling `handler(source_type)` to get the inner schema, then wrapping it with a `core_schema.with_info_after_validator_function(...)` (or the `no_info` variant, chosen automatically by inspecting whether the validator function accepts a second `info` argument). This is the extension mechanism for attaching reusable, composable validation/serialization logic to a *type* rather than duplicating a decorator on every model that uses that type — define once, reuse via `Annotated[int, MyValidator()]` everywhere.

**Discriminated unions** (a performance/UX pattern applicable to any tagged-union-like validation problem): a standard Pydantic union tries every member and scores results by "smart" match logic (`Exactness`, `fields_set_count`) — O(n) validation attempts and messy "anyOf" error output on failure. A discriminated union (`Discriminator` class, `apply_discriminator()` in `_internal/_discriminated_union.py`) instead extracts one designated field's value up front, looks it up in a pre-built `_tagged_union_choices` map, and validates against exactly that one member. Benefits: only one validation attempt (not n), and errors are specific to the identified variant instead of generic union noise. The `Discriminator` class supports either a plain string field name or a callable that extracts the discriminator from arbitrary input shapes.

**Trusted/untrusted construction split**: `model_construct(**values)` bypasses validation entirely — sets `__dict__` directly, processes aliases, fills in defaults for missing fields, still calls `model_post_init(None)`. Documented use case: performance-critical paths where data is already known-good (e.g., coming straight from your own database). This is a reusable pattern: separate "validate untrusted input" from "reconstruct from trusted internal source" as two different entry points with very different cost profiles, rather than always paying full validation cost.

**Error structure for debuggable validation failures**: every `ValidationError` detail dict carries `type` (machine-readable error code like `int_parsing`, `greater_than`), `loc` (tuple path to the failure, e.g. `('parent', 'child', 'field')` or `('my_list', 2)` for a list index or `('my_dict', 'key_name', '[key]')` for a dict key), `msg` (human-readable), `input` (the actual failing value), `ctx` (extra structured context, e.g. the `gt` threshold that was violated), and `url` (a docs link for that error type). This `(type, loc, msg, input, ctx, url)` shape is a good template for any system reporting structured validation errors instead of flat strings. `hide_input` on `ValidationError.from_exception_data` lets you suppress echoing the raw input value back in error output for security-sensitive fields.

**Raising errors from inside custom validators**: plain `ValueError`, `TypeError`, or `AssertionError` raised inside a `@field_validator`/`@model_validator` function are caught by Pydantic and wrapped into the final `ValidationError` automatically — no need to construct Pydantic-specific exception types for the common case. For structured/templated custom errors, `PydanticCustomError` (new error type with message template) and `PydanticKnownError` (trigger one of Pydantic's built-in error codes from Python code) are available from `pydantic_core`.

**Extra-field handling as a three-way policy**: `ConfigDict(extra=...)` takes `'ignore'` (default — silently drop unknown keys), `'forbid'` (raise `ValidationError` with type `extra_forbidden`), or `'allow'` (store unknowns in `__pydantic_extra__`, optionally type-checked if annotated). This is a clean, minimal API for a very common requirements-negotiation problem (strict schema vs. permissive schema vs. pass-through schema).

**Frozen models and field-level immutability**: `ConfigDict(frozen=True)` makes the whole instance immutable (generates `__hash__`, blocks `__setattr__`) via a `_check_frozen()` guard; `Field(frozen=True)` can freeze an individual field while leaving the rest of the model mutable. `__setattr__` dispatches to different handlers depending on field type: `model_field` (plain assignment), `validate_assignment` (re-run validation on assignment if `ConfigDict(validate_assignment=True)`), `private` (route to `__pydantic_private__`), `cached_property`, `extra_known`.

**Computed fields**: `@computed_field` on a `@property` includes a derived value in serialized output (`model_dump()`/JSON) without it being a stored field. Marked `readOnly: true` in generated JSON Schema — a clean way to expose derived data in an API response schema while making clear to consumers it isn't a settable input.

**`when_used` for context-sensitive serialization**: field/model serializers can be scoped with `when_used`: `'always'` (both `model_dump()` and `model_dump_json()`), `'json'` (JSON output only), `'unless-none'`, `'json-unless-none'`. Useful for fields that need different representations depending on target format (e.g., `datetime` as a Python object in `model_dump()` but as an ISO string in `model_dump_json()`).

**Rust-side performance techniques worth knowing about generally**: `pydantic-core` uses `ahash` (fast, non-cryptographic hashing) for `LiteralLookup`/`ModelFieldsValidator` field-name lookups; `SmallVec` in unions and error collection to avoid heap allocation for the common case of few elements; a custom JSON parser (`jiter`) tuned for validation workloads rather than generic parsing, enabling partial-JSON support and strict-mode checks during parsing itself rather than as a post-pass; a `LookupTree` structure that resolves field names/aliases efficiently even with multiple valid lookup paths per field.

## Practical how-tos

- **Define and validate a model**: `class User(BaseModel): id: int; name: str = 'Jane Doe'` then `User(id='123')` — the string `'123'` is coerced to `int` because of lax mode.
- **Validate arbitrary types without a model class**: use `TypeAdapter(list[Person])` and call `.validate_python(data)` / `.validate_json(data)` / `.dump_json(instance)` — useful for validating a bare list, dict, or scalar type where defining a full `BaseModel` subclass is overkill.
- **Validate function arguments**: `@validate_call` decorator on a plain function applies Pydantic validation to its parameters based on their type hints.
- **Custom field validation logic**: `@field_validator('field_name', mode='after') def check(cls, v): ...` — raise `ValueError` on failure, return the (possibly transformed) value on success.
- **Cross-field validation**: `@model_validator(mode='after') def check_passwords_match(self): ...` operating on the fully-built instance; use `mode='before'` if you need to inspect/mutate the raw input dict before field-level validation runs.
- **Dynamic model creation at runtime**: `create_model('DynamicUser', id=(int, ...), name=(str, 'Jane Doe'))` builds a `BaseModel` subclass programmatically — the `...` (Ellipsis) marks a field as required.
- **Resolve forward references**: call `model.model_rebuild()` after all referenced types are defined; it checks `__pydantic_complete__`, deletes the stale validator/serializer if incomplete or `force=True`, resolves the type namespace, and regenerates the schema.
- **Reusable validation/serialization logic on a type**: package it as `Annotated[int, AfterValidator(must_be_positive)]` and reuse that annotated type alias across models instead of copy-pasting a `@field_validator`.
- **Discriminated union for a tagged-variant field**: `Annotated[Union[Cat, Dog], Discriminator('pet_type')]` where `Cat`/`Dog` each have a `pet_type: Literal[...]` field — avoids O(n) union-member trial-and-error.
- **Programmatically inspect validation failures**: catch `ValidationError`, call `.errors()` for a list of structured dicts, `.json()` for a JSON string, `.error_count()` for a quick count; map `error['type']` to custom user-facing messages if you don't want Pydantic's default wording.

## Gotchas & caveats

- V1 method names raise `AttributeError` on V2 models unless you're deliberately on the compatibility path — the renames are: `__fields__`→`model_fields`, `.construct()`→`.model_construct()`, `.copy()`→`.model_copy()`, `.dict()`→`.model_dump()`, `.json()`→`.model_dump_json()`, `.parse_obj()`→`.model_validate()`, `.parse_raw()`→`.model_validate_json()`, `.update_forward_refs()`→`.model_rebuild()`. `@validator`/`@root_validator` (V1 decorators) still work in V2 but emit deprecation warnings and are internally shimmed into V2 `CoreSchema` constructs — don't write new code against them.
- A complete copy of the actual V1 codebase (not just a shim) ships under the `pydantic.v1` namespace for gradual migration (`from pydantic.v1 import BaseModel`). The automated `bump-pydantic` tool (a separate package using `LibCST` transforms) handles most of the mechanical renames, including `class Config:` → `model_config = ConfigDict(...)`.
- `pydantic._migration.getattr_migration` intercepts `AttributeError`s on legacy import paths (e.g. `pydantic.utils`) to redirect and warn rather than hard-fail immediately — don't assume an import succeeding at the top level means you're using current APIs; check for `PydanticDeprecatedSince20` warnings.
- `model_construct()` skips validation entirely — only use it with data you already trust (e.g., straight from your own DB), since it will happily construct an instance with type-invalid field values if you're not careful with defaults/aliases.
- `serialize_as_any` changes serialization to use the object's *actual runtime type* rather than its declared type-hint — an easy source of "why did extra fields show up in the output" surprises if used carelessly with subclassed models being passed where a base class is expected (this is also exactly the mechanism you'd want to *avoid* accidentally triggering if you rely on `response_model`-style field stripping, as in FastAPI).
- `PydanticUserError` (a `TypeError` subclass) signals *developer* mistakes in model/validator definition (e.g. `base-model-instantiated` for calling `BaseModel()` directly, `validator-signature` for a validator with the wrong number of arguments, `model-field-missing-annotation`) — distinct from `ValidationError`, which signals *data* mismatches. Don't conflate the two when writing exception handlers; catching `ValidationError` will not catch a misconfigured model.
- Field-validator function signatures are auto-detected (no-info `func(value)` vs. with-info `func(value, info)`) by inspecting the function at decoration time — an inconsistent or malformed signature surfaces as a `PydanticUserError`, not a validation-time error, so these bugs show up at import/class-definition time rather than when data actually flows through.

## Wiki pages used

- Overview
- Core Model System / BaseModel
- Field System
- Model Configuration
- Validators
- Serializers
- JSON Conversion (partial)
- Error Handling
- Discriminated Unions
- V1 to V2 Migration
- pydantic-core Rust Engine
