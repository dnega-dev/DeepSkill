---
repo: facebook/react
deepwiki: https://deepwiki.com/facebook/react
github: https://github.com/facebook/react
harvested: 2026-07-09
cluster: frontend-and-desktop
---

> Distilled from the DeepWiki wiki for [`facebook/react`](https://deepwiki.com/facebook/react) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# facebook/react — Distilled Knowledge

## What it is

React is a JavaScript library for building user interfaces, developed as a monorepo (Yarn Workspaces, `packages/*`) that hosts the core `react` package, the platform-agnostic reconciler (`react-reconciler`), the cooperative task `scheduler`, multiple rendering targets (`react-dom`, `react-native` via Fabric, `react-art`, `react-test-renderer`), the React Compiler (in `compiler/`), React DevTools, and supporting build/test tooling (Rollup, Jest, ESLint, Flow). As of the wiki snapshot, `ReactVersion.js` reports version 19.3.0.

The repo's layered dependency model: `react` (core API) → `react-reconciler` (Fiber algorithm) → `scheduler` (task prioritization) → renderers (`react-dom`, `react-native`, `react-test-renderer`, `react-art`) implement platform specifics on top of the reconciler. `react-compiler` statically transforms `react` source; `react-devtools` hooks into runtime internals; feature flags gate experimental code across all layers.

## Architecture (how it's built, key components)

**Fiber tree.** The UI is represented as a mutable tree of Fiber JS objects (`ReactFiber.js`, created via `createFiberImplClass`/`createFiberImplObject`). Each Fiber has: a `tag` (FunctionComponent, ClassComponent, HostComponent, SuspenseComponent, etc. — `ReactWorkTags.js`), a `stateNode` (class instance or host/DOM instance), tree pointers `return`/`child`/`sibling`, an `alternate` pointer to the other buffer (current vs. work-in-progress — double buffering), `flags` (side-effect bits), and `lanes` (priority bitmask).

**Two-phase work loop** (`ReactFiberWorkLoop.js`):
- *Render phase* — interruptible, no host mutations. `performUnitOfWork` drives `beginWork` (top-down: reconciles children, computes new props/state, invokes render logic per fiber type) then `completeWork` (bottom-up: creates/updates host instances, sets effect flags like `Placement`/`Update`/`ChildDeletion`, bubbles flags/lanes to parent). Errors call `unwindWork` to unwind to boundaries.
- *Commit phase* — synchronous, uninterruptible, run by `commitRoot`. Four ordered sub-stages: `commitBeforeMutationEffects` (snapshot/`getSnapshotBeforeUpdate`) → `commitMutationEffects` (actual DOM insert/delete/update, ref detach) → `commitLayoutEffects` (`componentDidMount`/`componentDidUpdate`, `useLayoutEffect`, ref attach — runs before browser paint) → `commitPassiveMountEffects` (`useEffect`, scheduled asynchronously after paint so it doesn't block interactions).

**Lane-based priority system** (`ReactFiberLane.js`). Priority is a bitmask ("lane"): `NoLanes`, `SyncLane`, `InputContinuousLane`, `DefaultLane`, transition lanes, `IdleLane`, `OffscreenLane`, `GestureLane`. Multiple pending updates at different priorities coexist on a fiber/root simultaneously; the scheduler chooses which lanes to render each pass, enabling concurrent/interruptible rendering rather than lock-step processing of one queue.

**Root scheduler.** Multiple roots are tracked in a linked list (`firstScheduledRoot`/`lastScheduledRoot`, `ReactFiberRootScheduler.js`). `ensureRootIsScheduled(root)` registers a root and marks pending sync work; a microtask (`ensureScheduleIsScheduled`) later calls `flushSyncWorkAcrossRoots_impl`, which iterates all scheduled roots and dispatches `performSyncWorkOnRoot` per root with pending lanes — batching updates across independent React roots in one microtask.

**Scheduler package** (standalone, in `packages/scheduler`). Six numeric priorities (`NoPriority=0` … `IdlePriority=5`) with timeouts (`ImmediatePriority` = -1ms/expires instantly, `UserBlockingPriority`=250ms, `NormalPriority`=5000ms, `LowPriority`=10000ms, `IdlePriority`≈2^30ms). Two min-heaps: `timerQueue` (delayed tasks ordered by `startTime`) and `taskQueue` (ready tasks ordered by `expirationTime`); `advanceTimers` migrates tasks from timer→task queue once eligible. The work loop (`flushWork`/`workLoop`) executes tasks, yields cooperatively to the host when a deadline is hit, and lets a callback return a continuation function to reschedule itself for incremental work. Host integration is abstracted via `requestHostCallback`/`requestHostTimeout`/`cancelHostTimeout` so the same scheduler works in browsers, React Native, etc. (there is also an experimental integration with the browser `postTask` API).

**Hooks — dispatcher pattern** (`ReactFiberHooks.js`). Hook calls (`useState`, `useEffect`, etc.) route through `ReactSharedInternals.H`, a global dispatcher reference resolved via `resolveDispatcher()`. Different dispatcher objects are swapped in depending on render context: `HooksDispatcherOnMount` (first render), `HooksDispatcherOnUpdate` (re-render), a server dispatcher in Fizz (`ReactFizzHooks.js`), and a debug dispatcher for DevTools inspection (`ReactDebugHooks.js`). Hooks form a singly linked list stored on `fiber.memoizedState`; each `Hook` node has `memoizedState`, `baseState`/`baseQueue` (for correctness under concurrent rendering with interleaved priorities), `queue` (pending updates), and `next`. During render, `currentHook` and `workInProgressHook` pointers walk this list in the same order the hooks were called — this is *why hook call order must be stable* across renders. State-bearing hooks (`useState`/`useReducer`) use a circular linked list of update objects tagged with lane + action + an "eager state" computed at dispatch time to short-circuit unnecessary re-renders.

**Host Config abstraction** (`ReactFiberConfig.js`). The reconciler itself is platform-agnostic; each renderer (DOM, Fabric/React Native, test-renderer) implements a fixed interface (`createInstance`, `commitUpdate`, hydration hooks, event system integration) that the reconciler core calls generically. This is the seam that lets one Fiber algorithm drive completely different backends.

**Suspense.** A component "suspends" by throwing a promise during render; the nearest `<Suspense fallback>` boundary catches it, renders the fallback, and retries when the promise resolves ("ping"). Suspense boundaries nest; React can hydrate a parent (and unaffected siblings) even while a child Suspense boundary is still suspended — enabling progressive/partial hydration instead of blocking the whole subtree. `SuspenseList` coordinates reveal order (`revealOrder`: forwards/backwards/together) and fallback tail behavior (`tail`) across multiple sibling Suspense boundaries. `lazy()` code-splitting is implemented on top of the same suspend/retry mechanism.

**Error boundaries.** Class components implementing `static getDerivedStateFromError(error)` and `componentDidCatch(error, info)` catch errors thrown during render/lifecycle/constructors in descendants. On error during concurrent render, React unwinds to the nearest boundary, calls `getDerivedStateFromError`, enqueues a fallback-rendering update, and can continue other fiber work asynchronously before committing the fallback — so one subtree's error doesn't collapse the whole app.

**Fizz (streaming SSR).** APIs: `renderToPipeableStream` (Node.js, returns `{pipe, abort}`, lifecycle callbacks `onShellReady`/`onShellError`/`onAllReady`/`onError`) and `renderToReadableStream` (Web Streams — browser/Edge/Bun, exposes an `allReady` promise). `prerender`/`resume` implement Partial Prerendering (PPR): `prerender` produces a static `prelude` stream plus a `postponed` state describing suspended "holes"; `resume` later continues rendering just those holes. Suspense boundaries stream as: placeholder+fallback HTML immediately, then out-of-order "instruction" script tags (`completeBoundary`, `completeSegment`, `clientRenderBoundary`, `formReplaying`) that the client uses to swap fallback→real content without a full reload. A "Float" resource-hoisting system tracks preconnects, font/image preloads, and stylesheets in `RenderState` and flushes them into `<head>` as early as possible (including via HTTP/2 `onHeaders`), independent of where they appear in the tree.

**Flight (React Server Components wire protocol).** `ReactFlightServer` serializes a React tree (elements, fragments, lazy components, async iterators, client/server references) into a streamable chunked format; suspending components (thrown promises) emit placeholder chunks that are later replaced as data resolves. `ReactFlightClient` parses the stream as a row-based state machine per chunk: `PENDING` → `BLOCKED` (dependencies unresolved) → `RESOLVED_MODEL` (JSON received, not parsed) → `INITIALIZED`. Client References are proxies for client-only code; Server References are callable server functions carrying bound-argument metadata, resolved through bundler-specific manifests (Webpack, Turbopack, ESM, Parcel each have integration points). Temporary references preserve object identity for transient values across the wire. A taint registry prevents accidental leakage of sensitive server values into client-bound serialization.

**Fabric (React Native renderer).** `ReactFabric` is the JS-side entry point: `render(element, containerTag, callback, concurrentRoot, options)` mounts into a native container ("surface"); `stopSurface` unmounts; `dispatchCommand` sends imperative native commands; `findNodeHandle`/`findHostInstance_DEPRECATED` bridge Fiber instances to native tags. Native components are described via `ViewConfig` objects (commands, constants, manager name, prop/attribute schema) that let the renderer create/update native views efficiently. The renderer talks to native code through `nativeFabricUIManager`, implementing the same Host Config interface pattern used by react-dom.

**React Compiler pipeline** (in `compiler/`, separate sub-monorepo). Orchestrated by `runWithEnvironment` (`Pipeline.ts`): (1) **Lowering** — Babel AST → HIR, an explicit control-flow graph of `BasicBlock`s made of `Instruction`s referencing `Place`s; (2) **SSA transform** (`enterSSA`) — each variable assigned exactly once, with `Phi` nodes at CFG merge points, to make data flow explicit; (3) **Inference passes** — type inference, constant propagation, dead-code elimination, mutability/aliasing analysis; (4) **Reactive scope inference** — identifies which values are memoizable by analyzing mutable ranges and dependency graphs, merging/pruning scopes; (5) **ReactiveFunction construction** — flat SSA HIR rebuilt into a tree of nested reactive-scope blocks (`buildReactiveFunction`); (6) **Codegen** — emits Babel AST with inserted memoization/caching infra and Fast Refresh compatibility (`codegenFunction`). A central `Environment` class (`Environment.ts`) tracks a global registry of known browser/React/custom-hook APIs used during inference.

## Key patterns & techniques (transferable knowledge)

- **Double buffering via `alternate` pointers.** Keep two versions of a tree (current vs. work-in-progress) linked pairwise so you can build/mutate the new tree without touching the live one, then swap roots atomically at commit. General pattern for any incremental/interruptible tree-diffing engine.
- **Split "compute" (interruptible) from "apply" (atomic) phases.** Render phase produces a plan (effect list/flags) with zero observable side effects; commit phase executes that plan synchronously in one shot. This is what makes concurrent rendering possible without visible tearing — you can abandon/restart the compute phase freely because nothing external has been touched yet.
- **Priority as a bitmask ("lanes"), not a single queue.** Multiple pending updates at different urgencies can be tracked and combined with bitwise ops; lets you answer "what's the highest priority pending?" or "should I include this transition in the current render pass?" cheaply.
- **Cooperative scheduling via min-heaps + host-provided yielding hooks.** Two heaps (delayed vs. ready) plus an abstract `requestHostCallback`/`shouldYield` seam decouples the scheduling algorithm from the specific runtime (browser rAF/idle callbacks, React Native's bridge, `postTask`), so the same core scheduler ports across environments.
- **Dispatcher indirection for context-dependent behavior.** Rather than branching every hook implementation on "are we mounting, updating, on the server, or being inspected by devtools", swap a single global dispatcher object per context. Each concrete dispatcher implements the same interface; call sites stay simple.
- **Linked-list-per-instance state, not a state object.** Hooks are a singly linked list hung off the fiber, walked in call order every render — this is the underlying reason the "rules of hooks" (no conditional hooks) exist: the list has no keys, only position.
- **Suspend-by-throwing-a-promise as a control-flow primitive.** Any async boundary (data fetch, lazy import, async Server Component) is unified under "throw a promise, catch it at a declarative boundary, retry on resolution" instead of prop-drilling loading states. Reusable outside React for any incremental/streaming render pipeline.
- **Streaming with out-of-order "instruction" patches.** Fizz sends the synchronous "shell" first, then patches in async segments via small inlined `<script>` instructions that mutate specific DOM ids in-place — decouples network arrival order from document order, letting slow subtrees not block fast ones.
- **Resource-hoisting float pattern.** Track resource requirements (preloads, stylesheets) in a side structure decoupled from render position, and flush them at the earliest valid point in the document, independent of component tree depth.
- **HIR/SSA/CFG-based compiler pipeline for a source-to-source optimizer.** Rather than optimizing directly over an AST, lower into an explicit control-flow graph with SSA form to make aliasing/mutation analysis tractable, then reconstruct a higher-level tree for codegen. Applicable to any auto-memoization or auto-optimization compiler for a dynamic language.
- **Host Config seam for multi-target architecture.** Keep one algorithmic core with a narrow, fixed interface (create/update/delete instance + hydration + events) and implement that interface per target. Lets DOM, native mobile, and test renderers all reuse the same reconciliation logic.

## Practical how-tos

- **Reasoning about a render bug**: trace whether the issue is in the render phase (wrong beginWork/completeWork output — check hook order or memoization deps) or the commit phase (wrong effect flag or wrong sub-phase — before-mutation vs mutation vs layout vs passive timing matters, e.g. `useLayoutEffect` runs before paint, `useEffect` after).
- **Debugging hook-order violations**: because hooks are a positional linked list (no keys), any hook called conditionally will misalign `currentHook`/`workInProgressHook` on the next render — this manifests as one hook's state being read into another's.
- **Choosing an SSR streaming API**: use `renderToPipeableStream` for Node.js (`pipe()` handles backpressure via the writable's `drain` event); use `renderToReadableStream` for Web-Streams-native runtimes (browser/Edge/Bun) with an `allReady` promise to know when the full tree is ready; use `prerender`/`resume` (PPR) when you want to precompute a static shell and defer only the async holes.
- **Wrapping async data in Suspense**: implement a read function that throws a pending promise (cache-miss) or returns synchronously resolved data (cache-hit) — that's the entire contract `Suspense` boundaries expect; no special React API needed beyond a `Suspense fallback={...}` wrapper.
- **Coordinating multiple loading regions**: use `SuspenseList` with `revealOrder` and `tail` instead of manually sequencing several independent `Suspense` boundaries.
- **Tracing an RSC request**: `ReactFlightServer` emits chunks tagged by type (model / client-ref / server-ref / error); on the client, `ReactFlightClient` chunk state moves PENDING → BLOCKED → RESOLVED_MODEL → INITIALIZED — a stuck request usually means a chunk is stuck BLOCKED on an unresolved dependency.
- **Adding a new host environment**: implement the Host Config interface (`ReactFiberConfig.js` contract: createInstance, commitUpdate, hydration, event system) rather than touching the reconciler.

## Gotchas & caveats

- Hook call order must be identical across renders because hooks are a positional linked list with no identity/keys — conditional or looped hook calls silently corrupt state.
- Commit-phase sub-stages have a fixed, meaningful order (before-mutation → mutation → layout → passive); `useLayoutEffect` blocking paint is intentional (synchronous, pre-paint) whereas `useEffect` deliberately runs after paint asynchronously — conflating the two changes visible behavior (flicker vs. no flicker).
- Render phase must stay side-effect-free (no host mutations) because it can be interrupted/abandoned/replayed under concurrent rendering; doing host writes there breaks the double-buffering guarantee.
- Partial hydration means a suspended Suspense boundary does not block hydration of parent/sibling content — code relying on "everything above me in the tree is already interactive" during hydration can be wrong.
- Flight's taint registry exists specifically because server-only sensitive values can otherwise leak into the client-bound serialized payload — RSC boundaries are not automatically safe without explicit tainting.
- Bundler integration for Flight (Webpack/Turbopack/ESM/Parcel) is not uniform — each has its own manifest/reference-resolution mechanism, so RSC support depth varies by bundler.
- The React Compiler's HIR/SSA pipeline (compiler/) is a separate, actively evolving sub-monorepo with its own validation passes and even a Rust port in progress per the wiki structure — treat compiler internals as more volatile than the stable reconciler.

## Wiki pages used

- React Repository Overview
- Core Reconciler Architecture
- Fiber Work Loop and Scheduling
- Hooks Implementation
- Suspense, Error Boundaries, and Concurrent Features
- Scheduler Package
- Server-Side Rendering: Fizz
- React Server Components: Flight Protocol
- React Native Renderer (Fabric)
- Compiler Pipeline and HIR
