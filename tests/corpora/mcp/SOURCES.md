# MCP corpus: protocol sources

Where each MCP protocol fact in PRD-023 comes from. PRD-023 puts an MCP
gateway in the harness: northbound it serves `/mcp` to coding agents, southbound
it is an MCP client of upstream servers. Both halves depend on wire facts
(version negotiation, session headers, error codes, tool names, capabilities).
Each fact below was read from the spec's own source pages, not from a summary.
STORY-002 appends the client survey and STORY-003 the SDK pin; this section
(STORY-001) is the protocol only.

Everything was fetched on **2026-11-22** (STORY-001), from the repository
`modelcontextprotocol/modelcontextprotocol`, with `gh api` and the raw page
source. Every link below is pinned to a **40-hex commit** that the release tag
of that revision points to (see the table), so a later edit of the spec cannot
change what this file says. Never `latest`, `draft` or a branch. A statement
quoted in "double quotes" is the spec's own wording (MUST/SHOULD kept).

A fact is one of two kinds. **resolved**: read and quoted from a pinned page.
**limitation**: not verified, or the spec is silent; the safe default is stated
and is what the PRD must assume.

## Protocol

### Revisions

The status words are the spec's: *Draft* "in-progress specifications, not yet
ready for consumption", *Current* "the current protocol version, which is ready
for use and may continue to receive backwards compatible changes", *Final*
"past, complete specifications that will not be changed" ([versioning][ver-main],
[the same text in the revision][ver-2026]).

| Revision | Tag -> commit | Status on 2026-11-22 | Era | Negotiation |
|---|---|---|---|---|
| `2026-07-28` | `2026-07-28` -> `5f5440bb26a62e2cf3440b92da5a667efa03b267` | **Current** (quoted: "The **current** protocol version is **2026-07-28**") | modern | none: every request carries its version in `_meta`; unsupported -> `UnsupportedProtocolVersionError` (`-32022`) |
| `2025-11-25` | `38c84e9f93ad191d9eb26d92b945d17bd0efcaf3` | Final (by the definition above; the page does not label it) | legacy | `initialize` handshake |
| `2025-06-18` | `f5ccad944fdf2b7d9cc70cf817f66ca5a8aa03a4` | Final (same) | legacy | `initialize` handshake |
| `2025-03-26` | `9236eb1cbfa02c17ab45c83a7bdbe55c450070be` | Final (same) | legacy | `initialize` handshake |
| `draft` | directory `docs/specification/draft` exists at `862397cec702e8f828713071da501cf56158e8fc` | Draft; **not read, not supported** | | |

`2024-11-05` (HTTP+SSE) is out of scope: the spec deprecates that transport
([2026-07-28 deprecated registry][dep-2026]).

The terms "modern" (`2026-07-28` and later) and "legacy" (`2025-11-25` and
earlier), and "dual-era" for an implementation that supports both, are the
spec's own ([versioning, Terminology][ver-2026]).

**Handshake rule, legacy revisions** ([2025-11-25 lifecycle][life-1125]): "In the
`initialize` request, the client **MUST** send a protocol version it supports."
"If the server supports the requested protocol version, it **MUST** respond with
the same version. Otherwise, the server **MUST** respond with another protocol
version it supports. This **SHOULD** be the _latest_ version supported by the
server." This is the rule D17 needs: **the newest supported legacy version is
answered when the client's is unknown.**

**Per-request rule, modern** ([versioning][ver-2026]): "If the server does not
implement the requested version ... it **MUST** respond with an
`UnsupportedProtocolVersionError` listing the versions it does support"
(`code -32022`, `data: {supported: [...], requested: "..."}`); "Servers **MUST**
implement `server/discover`."

### The 15 facts

| # | Fact | Result | Kind | Source |
|---|---|---|---|---|
| 1 | Supported revision strings (D17) | The strings are `2025-03-26`, `2025-06-18`, `2025-11-25` (handshake) and `2026-07-28` (per-request). `2026-07-28` is the **current** revision, not `2025-11-25` as PRD 6.1 and D17 assume. Whether the harness serves `2026-07-28` is a design decision, not a fact: see "Serving each era" below | resolved | [versioning][ver-main], [2026 changelog][chg-2026] |
| 2 | JSON-RPC batching removed in `2025-06-18` | Yes. `2025-03-26` added it ("Added support for JSON-RPC **batching**"); `2025-06-18` changelog item 1: "Remove support for JSON-RPC **batching**". `2025-03-26` transports let the POST body be an array; `2025-06-18` and `2025-11-25` say "The body of the POST request **MUST** be a single JSON-RPC _request_, _notification_, or _response_"; `2026-07-28` says "a single JSON-RPC _request_ or _notification_". Batching never returns. So a `2025-03-26` client may send an array body | resolved | [03-26 changelog][chg-0326], [06-18 changelog][chg-0618], [11-25 transports][tr-1125], [2026 streamable-http][tr-2026] |
| 3 | Header spellings | `MCP-Protocol-Version` (from `2025-06-18`; `2025-03-26` has no such header: zero occurrences). Session header: `Mcp-Session-Id` in `2025-03-26` and `2025-06-18`, **`MCP-Session-Id`** in `2025-11-25` (only the spelling changed). `2026-07-28`: `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`, and `Mcp-Param-{Name}`; session header removed. Case rule: `2026-07-28` states "Header names ... are case-insensitive. Clients and servers **MUST** use case-insensitive comparisons for header names. Header _values_ (such as method names) are case-sensitive." The earlier revisions state no case rule; HTTP field names are case-insensitive (RFC 9110, which `2026-07-28` cites). Compare names case-insensitively, emit `Mcp-Session-Id` only if ever needed | resolved | [03-26 transports][tr-0326], [06-18 transports][tr-0618], [11-25 transports][tr-1125], [2026 streamable-http][tr-2026] |
| 4 | Expired session -> 404; does 404 mean "not processed" (T10) | The 404 rule is in the three legacy revisions: "The server **MAY** terminate the session at any time, after which it **MUST** respond to requests containing that session ID with HTTP 404 Not Found." "When a client receives HTTP 404 in response to a request containing an `MCP-Session-Id`, it **MUST** start a new session by sending a new `InitializeRequest` without a session ID attached." **The spec does not say the request was not processed.** It says only that the session is gone. PRD T10's "which by spec means the request was not processed" is **not supported by the spec**. Safe default: a 404 is evidence the server did not know the session, not a guarantee that a forwarded `tools/call` did not run (an intermediary can return a 404 after upstream work). Do not auto-retry a `tools/call` on a 404; re-initialize for the *next* call. Under `2026-07-28` no session and no such 404 exist | resolved (rule) / limitation (not-processed) | [11-25 transports, Session Management][tr-1125] |
| 5 | A stateless server may omit the session header | Yes, legacy: "A server using the Streamable HTTP transport **MAY** assign a session ID at initialization time" (`MAY`; `2025-03-26`, `2025-06-18` and `2025-11-25` all say it) and the client's duty is conditional: "If an `MCP-Session-Id` is returned by the server during initialization, clients ... **MUST** include it". `2026-07-28` removes sessions: "Remove protocol-level sessions and the `Mcp-Session-Id` header from the Streamable HTTP transport", and a modern-only server receiving a session header "**SHOULD** ... ignore it, and do not mint or echo session IDs" | resolved | [11-25 transports][tr-1125], [2026 changelog][chg-2026], [2026 streamable-http, Earlier Revisions][tr-2026] |
| 6 | `InitializeResult.instructions` | `instructions?: string` exists in `InitializeResult` in `2025-03-26` (the earliest revision read), `2025-06-18` and `2025-11-25`: "Instructions describing how to use the server and its features. ... this information MAY be added to the system prompt." Under `2026-07-28` there is no `initialize`; the equivalent is `DiscoverResult.instructions?: string` (the `server/discover` result). Not carried on `tools/list` | resolved | [03-26 schema][sch-0326], [06-18 schema][sch-0618], [11-25 schema][sch-1125], [2026 schema][sch-2026], [2026 discover][disc-2026] |
| 7 | Tool-name charset and length (O7) | Guidance exists only from `2025-11-25` (changelog: "Provide guidance on tool names"); `2025-03-26` and `2025-06-18` give none. `2025-11-25` and `2026-07-28` agree: names "**SHOULD** be between 1 and 128 characters"; "case-sensitive"; "The following **SHOULD** be the only allowed characters: uppercase and lowercase ASCII letters (A-Z, a-z), digits (0-9), underscore (\_), hyphen (-), and dot (.)"; "**SHOULD NOT** contain spaces, commas, or other special characters"; "**SHOULD** be unique within a server". So `__` and `-` are both allowed, and `.` is allowed too. All SHOULD, not MUST. `2026-07-28` also says an aggregating proxy "**SHOULD** implement a disambiguation strategy such as prefixing tool names with a server identifier" and "The server `name` ... **SHOULD NOT** be relied upon for disambiguation" (so a prefix the operator controls, like the config's server id, is the spec-endorsed shape). **Client limit not in the spec:** the pinned client sources in `tests/corpora/actions/SOURCES.md` (lines 80, 160) show OpenCode sanitizing outside `[a-zA-Z0-9_-]` and Cline truncating names over 64 characters with a hash suffix, so a `.` and a name over 64 characters are the risk. `<server>__<tool>` with a 32-char server id leaves 30 for the tool: limitation, confirmed per client in STORY-002 | resolved (spec) / limitation (clients) | [11-25 changelog][chg-1125], [11-25 tools][tools-1125], [2026 tools][tools-2026] |
| 8 | Unknown-tool error and the protocol-error / `isError` split | Unknown tool is a **protocol error**, JSON-RPC `-32602`: `{"code": -32602, "message": "Unknown tool: invalid_tool_name"}` (the example in `2025-03-26`, `2025-06-18`, `2025-11-25` and `2026-07-28`). Tool-execution failures are results with `isError: true` ("API failures, Input validation errors ..., Business logic errors"). `2025-11-25` changelog: "input validation errors should be returned as Tool Execution Errors rather than Protocol Errors". `2026-07-28` also puts `"resultType": "complete"` in the `isError` result | resolved | [03-26 tools][tools-0326], [06-18 tools][tools-0618], [11-25 tools][tools-1125], [2026 tools][tools-2026] |
| 9 | `Origin` validation and the 403 wording (T11) | `2025-03-26`: no Origin requirement (no mention). `2025-06-18`: "Servers **MUST** validate the `Origin` header on all incoming connections to prevent DNS rebinding attacks" (no status code). `2025-11-25` and `2026-07-28`: the same, plus "If the `Origin` header is present and invalid, servers **MUST** respond with HTTP 403 Forbidden. The HTTP response body **MAY** comprise a JSON-RPC _error response_ that has no `id`." The rule is about a *present and invalid* `Origin`; an absent `Origin` is not refused by the spec | resolved | [06-18 transports][tr-0618], [11-25 transports][tr-1125], [2026 streamable-http][tr-2026], [11-25 changelog][chg-1125] |
| 10 | `notifications/cancelled` | The cancellation method in all legacy revisions (`2025-11-25`: "To cancel, the client **SHOULD** explicitly send an MCP `CancelledNotification`"; a dropped connection "**SHOULD NOT** be interpreted as the client cancelling its request"). **Under `2026-07-28` on Streamable HTTP it is not used:** "Closing the SSE response stream **MUST** be treated by the server as cancellation of that request"; `notifications/cancelled` is for stdio, and a server uses it only to end a `subscriptions/listen` stream. So a southbound forward must, per revision, either send `notifications/cancelled` (legacy) or close the response stream (modern). A northbound server may ignore a cancel: "Servers **MAY** ignore cancellation notifications if: The referenced request is unknown; Processing has already completed" | resolved | [11-25 transports][tr-1125], [2026 cancellation][canc-2026], [2026 streamable-http][tr-2026] |
| 11 | T12: sampling, roots, elicitation, tasks; MRTR | See "T12 verdict". Summary: a client that declares no capabilities is never sent these by a conformant server, in either era | resolved | see below |
| 12 | 9.1: spec-following client on `401` without `resource_metadata` | `2025-11-25`: servers "**MUST** implement OAuth 2.0 Protected Resource Metadata"; clients "**MUST** ... use the resource metadata URL from the parsed `WWW-Authenticate` headers when present; otherwise, they **MUST** fall back to constructing and requesting the well-known URIs", first the MCP-endpoint path, then the root; if neither exists the diagram says "Abort or use pre-configured values". `2025-11-25` changelog: "making `WWW-Authenticate` header optional with fallback to `.well-known` endpoint". Authorization itself is "**OPTIONAL**" in every revision. So a `401` with no metadata makes a spec-following client probe `/.well-known/oauth-protected-resource[/mcp]`, then abort. Whether OpenCode and Cline instead accept a static `Authorization` header and never start OAuth: not verified here (STORY-002). Safe default: serve a `401` with `WWW-Authenticate: Bearer` and no `resource_metadata`, and treat static-header support as unverified until STORY-002 | resolved (spec) / limitation (clients) | [11-25 authorization][auth-1125], [11-25 changelog][chg-1125], [2026 authorization][auth-2026] |
| 13 | Tool `annotations` are hints; content block types; `resource_link` | Annotations are hints: "clients **MUST** consider tool annotations to be untrusted unless they come from trusted servers" (`2025-06-18`, `2025-11-25` and `2026-07-28`). `ToolAnnotations` (`readOnlyHint` etc.) are advisory only, so the harness must never grant on them. `content[]` types: `text`, `image`, `audio`, `resource_link` (added in `2025-06-18`), embedded `resource`; plus `structuredContent` (from `2025-06-18`). `2025-03-26` has no `resource_link` and no `structuredContent`. `2026-07-28` loosens `structuredContent` to "any JSON value" | resolved | [06-18 changelog][chg-0618], [11-25 tools][tools-1125], [2026 tools][tools-2026], [2026 schema][sch-2026] |
| 14 | `tools/list` pagination, `listChanged`, `ttlMs` / `cacheScope` | Pagination is cursor-based in all revisions (`params.cursor`, `result.nextCursor`; "Page size is determined by the server, and clients **MUST NOT** assume a fixed page size"). `listChanged` is a `tools` capability flag with `notifications/tools/list_changed` in the legacy revisions. `2026-07-28`: `tools/list` results **MUST** carry `ttlMs` (>= 0) and `cacheScope` (`public` or `private`): "Servers **MUST** provide a `ttlMs` value that is `>= 0`" ("Require `ttlMs` and `cacheScope` fields on results returned by `tools/list`"); list-change notifications move to `subscriptions/listen` (a `toolsListChanged` opt-in). `tools/list` no longer varies per connection ("List endpoints ... no longer vary per-connection"); "Servers **SHOULD** return tools from `tools/list` in a deterministic order" | resolved | [11-25 tools][tools-1125], [2026 tools][tools-2026], [2026 caching][cache-2026], [2026 pagination][pag-2026], [2026 changelog][chg-2026] |
| 15 | Streamable HTTP POST rules | Legacy: the client "**MUST** include an `Accept` header, listing both `application/json` and `text/event-stream`"; a request gets "either `Content-Type: text/event-stream` ... or `Content-Type: application/json`, to return one JSON object. The client **MUST** support both"; a notification or response gets "HTTP status code 202 Accepted with no body"; an error is "an HTTP error status code (e.g., 400 Bad Request)". So a **JSON-only server is allowed** (and a JSON-only client is not: clients must accept both). `2026-07-28` keeps all of this and adds: `Mcp-Method` on all requests and `Mcp-Name` on `tools/call`, `resources/read`, `prompts/get` ("These headers are **REQUIRED** for compliance"); a header/body mismatch or a missing required header -> `400` with `HeaderMismatch` `-32020`; an unsupported version -> `400` with `-32022`; an unknown method -> `404` with `-32601`; a modern-only server "**SHOULD**" answer `GET` and `DELETE` with `405`; no `Last-Event-ID`; a modern server "**MUST NOT** send independent JSON-RPC _requests_ on this stream" | resolved | [11-25 transports][tr-1125], [2026 streamable-http][tr-2026] |

### Per-revision differences that change the design

| Topic | `2025-03-26` | `2025-06-18` | `2025-11-25` | `2026-07-28` |
|---|---|---|---|---|
| Open | `initialize` + `notifications/initialized` | same | same | none; `_meta` on every request; `server/discover` mandatory |
| Version carried | in the handshake only | handshake + `MCP-Protocol-Version` header | same | `_meta` + `MCP-Protocol-Version` header (must match) |
| Session id | `Mcp-Session-Id`, MAY | `Mcp-Session-Id`, MAY | `MCP-Session-Id`, MAY | removed |
| `ping` | yes | yes | yes | **removed** (also `logging/setLevel`) |
| Batching | array body allowed | removed | removed | removed |
| Result envelope | plain | plain | plain | `resultType` required (`"complete"` / `"input_required"`) |
| Server-to-client requests | on SSE streams | same | same | **forbidden**; replaced by MRTR `input_required` |
| `GET` stream, `DELETE` | yes | yes | yes | removed (SHOULD `405`) |
| `Origin` rule | none | MUST validate | MUST validate, 403 | MUST validate, 403 |
| Tool-name guidance | none | none | SHOULD 1-128, `[A-Za-z0-9_.-]` | same |
| Cancellation | `notifications/cancelled` | same | same | stream close (HTTP); notification only on stdio |

### Serving each era (facts for the northbound decision, not a decision)

A **handshake-only** northbound `/mcp` (`2025-03-26` .. `2025-11-25`), stateless:
answer `initialize` with a supported version and **no** session header (fact 5),
answer `notifications/initialized` with `202`, answer `ping` with `{}` (legacy
`ping`: "The receiver **MUST** respond promptly with an empty response"), answer
`tools/list` and `tools/call`, and return `405` to `GET`/`DELETE` ("The server
**MAY** respond to this request with HTTP 405 Method Not Allowed" is allowed for
`DELETE`; for `GET` the spec says the server "**MUST** either return
`Content-Type: text/event-stream` ... or return HTTP 405"). This is what
`2025-11-25` says a server may be.

A **modern** northbound additionally needs: `server/discover` (`supportedVersions`,
`capabilities`, `instructions`, `ttlMs`, `cacheScope`); per-request `_meta`
version and client-capability parsing; the three required headers and
`HeaderMismatch`; `UnsupportedProtocolVersionError`; `resultType` and
`ttlMs`/`cacheScope` on every result; no `ping`. The spec explicitly allows both
on one endpoint: "A dual-era **server** selects its behavior from how the client
opens: A request carrying modern per-request `_meta` is served statelessly ...
An `initialize` request selects legacy semantics" and "A dual-era server **MAY**
serve both eras concurrently on the same endpoint" ([versioning][ver-2026]).

**Refusing `2026-07-28` cleanly.** The spec's compatibility matrix says a legacy
(handshake-only) server and a dual-era client work together when "the modern
request returns a `4xx` without a recognized modern error body, and the client
falls back to `initialize`"; and "A server that supports only modern versions
**SHOULD** name the protocol versions it supports in any error it returns to an
`initialize` request". A handshake-only server that wants a *modern-only* client
to learn why should return `UnsupportedProtocolVersionError` with `supported`
listing the legacy revisions; whether a modern-only client then retries with a
legacy version (it has no `initialize` path) is **not verified**. For a dual-era
client the plain `4xx` without a modern error body is the spec-defined trigger to
fall back; returning a recognized modern error would instead tell it "this is a
modern server" ([streamable-http, Backward Compatibility][tr-2026]). Safe default
for option (a): answer a request that carries modern `_meta` with `400` and a
plain JSON-RPC `-32600` body (no modern error code), so a dual-era client falls
back to `initialize`.

### Verdicts on T10, T11, T12

- **T10 (ambiguous outcomes): CORRECT.** Never retried by the harness, "may have
  run": confirmed and applies to every revision. The sentence "the single safe
  retry is re-`initialize` after the server reports an unknown session, which by
  spec means the request was not processed" is **wrong** as written: (a) the spec
  says nothing about "not processed" (fact 4); (b) the re-initialize rule exists
  only in the legacy revisions; under `2026-07-28` there is no session and no
  unknown-session reply, so every post-forward failure is "may have run". Safe
  default: re-initialize for the next call, never replay the forwarded
  `tools/call`.
- **T11 (DNS rebinding): CONFIRMED.** The spec requires exactly "validate `Origin`;
  present and invalid -> 403" (fact 9). The treatment (a present `Origin` must be
  on `MCP_ALLOWED_ORIGINS`, default empty) is stricter than the spec and
  compatible with it. "CLI agents send none" is not verified here (STORY-002).
- **T12 (server-to-client channels): CONFIRMED, with one addition.**
  - Legacy: "Both parties **MUST**: Respect the negotiated protocol version; Only
    use capabilities that were successfully negotiated"
    ([11-25 lifecycle][life-1125]); "Clients that support sampling **MUST**
    declare the `sampling` capability" and "Servers **MUST NOT** send elicitation
    requests with modes that are not supported by the client"
    ([sampling][samp-1125], [elicitation][elic-1125]). A conformant upstream never
    sends `sampling/createMessage`, `elicitation/create` or `roots/list` to a
    client that declared none. If one does anyway, JSON-RPC `-32601` (the PRD's
    treatment) is the standard answer for a method the client does not offer.
  - Tasks (`2025-11-25`, experimental): "Tasks are designed to be
    **requestor-driven** - requestors are responsible for augmenting requests with
    tasks" ([tasks][tasks-1125]); the harness never augments a `tools/call`, so no
    task handle is expected back.
  - **Modern (`2026-07-28`, the addition):** server-to-client requests are replaced
    by MRTR. "Servers **MUST NOT** send an `inputRequests` that the client has not
    declared support for in its capabilities" and "Servers **MUST** include at
    least one of `inputRequests` or `requestState` in every `InputRequiredResult`"
    ([MRTR][mrtr-2026]); a server that needs a capability the client did not
    declare "**MUST** return a `MissingRequiredClientCapabilityError` (`-32021`)"
    ([basic][basic-2026]). MRTR applies to `tools/call` ("`tools/call` | Yes"), so
    an upstream **can** answer a southbound `tools/call` with
    `resultType: "input_required"`. The harness cannot answer it (no
    capabilities), so it must **refuse it as a stated outcome**, not return it
    northbound as a normal result and not retry it; the retry is a *new* request
    with a new id ("The JSON-RPC `id` **MUST** be different"), i.e. a second
    execution, so it falls under T10. Northbound, the harness declares nothing in
    `server/discover` that would let a client expect MRTR.
  - Sampling, roots and logging are **Deprecated** in `2026-07-28`
    ([registry][dep-2026]): "new implementations should not add support for them".
    This supports the PRD's "declare no capabilities".

### Legacy and modern facts the harness must not assume

- A `2025-03-26` client sends no `MCP-Protocol-Version`: "if the server does _not_
  receive an `MCP-Protocol-Version` header ... the server **SHOULD** assume
  protocol version `2025-03-26`" ([11-25 transports][tr-1125]); the modern
  revision lets a server "**MAY** treat a request that omits the header as
  protocol version `2025-03-26`" ([2026 streamable-http][tr-2026]).
- An invalid or unsupported `MCP-Protocol-Version` on a legacy revision: "it
  **MUST** respond with `400 Bad Request`" ([11-25 transports][tr-1125]).
- `Mcp-Name` may be Base64-encoded under a sentinel when the name is not safe
  ASCII ([2026 streamable-http, Value Encoding][tr-2026]); a tool id `__`-joined
  from ids that match `[a-z0-9-]` is plain ASCII.

### Not verified here

- Whether OpenCode and Cline send a static `Authorization` header without trying
  OAuth (fact 12) and which revision each negotiates: resolved by STORY-002, see
  `## Clients` below (both observed: static header sent, no OAuth discovery,
  `2025-11-25`). Correction to the SDK-pin guess above: OpenCode 2.3.2 depends on
  the v2 TS SDK (`@modelcontextprotocol/client` 2.4.0), not on v1.29.x.
- The `draft` directory (the next revision): not read.
- Whether a modern-only client retries a legacy version after
  `UnsupportedProtocolVersionError` (see "Refusing").
- The SDK version to use southbound: STORY-003.

[ver-main]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/862397cec702e8f828713071da501cf56158e8fc/docs/docs/2026-07-28/learn/versioning.mdx
[ver-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/basic/versioning.mdx
[dep-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/deprecated.mdx
[chg-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/changelog.mdx
[chg-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/changelog.mdx
[chg-0618]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/f5ccad944fdf2b7d9cc70cf817f66ca5a8aa03a4/docs/specification/2025-06-18/changelog.mdx
[chg-0326]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/9236eb1cbfa02c17ab45c83a7bdbe55c450070be/docs/specification/2025-03-26/changelog.md
[tr-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/basic/transports/streamable-http.mdx
[tr-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/basic/transports.mdx
[tr-0618]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/f5ccad944fdf2b7d9cc70cf817f66ca5a8aa03a4/docs/specification/2025-06-18/basic/transports.mdx
[tr-0326]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/9236eb1cbfa02c17ab45c83a7bdbe55c450070be/docs/specification/2025-03-26/basic/transports.md
[life-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/basic/lifecycle.mdx
[tools-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/server/tools.mdx
[tools-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/server/tools.mdx
[tools-0618]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/f5ccad944fdf2b7d9cc70cf817f66ca5a8aa03a4/docs/specification/2025-06-18/server/tools.mdx
[tools-0326]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/9236eb1cbfa02c17ab45c83a7bdbe55c450070be/docs/specification/2025-03-26/server/tools.md
[sch-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/schema/2026-07-28/schema.ts
[sch-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/schema/2025-11-25/schema.ts
[sch-0618]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/f5ccad944fdf2b7d9cc70cf817f66ca5a8aa03a4/schema/2025-06-18/schema.ts
[sch-0326]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/9236eb1cbfa02c17ab45c83a7bdbe55c450070be/schema/2025-03-26/schema.ts
[disc-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/server/discover.mdx
[canc-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/basic/patterns/cancellation.mdx
[mrtr-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/basic/patterns/mrtr.mdx
[basic-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/basic/index.mdx
[cache-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/server/utilities/caching.mdx
[pag-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/server/utilities/pagination.mdx
[auth-2026]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/docs/specification/2026-07-28/basic/authorization/index.mdx
[auth-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/basic/authorization.mdx
[samp-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/client/sampling.mdx
[elic-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/client/elicitation.mdx
[tasks-1125]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/38c84e9f93ad191d9eb26d92b945d17bd0efcaf3/docs/specification/2025-11-25/basic/utilities/tasks.mdx

## Clients

STORY-002 (2026-11-22): how OpenCode and Cline connect to a remote Streamable
HTTP MCP server with a static bearer header, and how they name its tools. Two
kinds of evidence, and every claim says which:

- **source**: the client's code at a pinned tag and 40-hex commit (links below).
- **observed**: the installed client, run on this machine (Windows 11) against a
  throwaway logging listener on `127.0.0.1` and a fake OpenAI-compatible
  provider that records `tools[]`. Isolated home and data directory, the dummy
  token `test-token`, no real key, every child killed as a tree and no listener
  left. Neither the listener nor the drivers are committed; the request lines
  quoted below are copied from their logs (token is the dummy). A run lasts a
  few seconds: a client that gives up on a `401` inside that window is recorded
  as "no retry within the run", not as "never".

### Versions surveyed

| Client | Version | Tag | Commit | Date | Licence | Notes |
|---|---|---|---|---|---|---|
| OpenCode (installed, the target) | `v2.3.2` (`opencode --version`; `@opencode/cli` binary) | `v2.3.2` | `c0ad18b402eb2827fc1ee71c171b1177b3fc02d1` | 2026-11-18 | MIT | `anomalyco/opencode`. The PRD names `2.0.10`: see "2.0.10" below |
| OpenCode (PRD-021's pin) | `v2.0.10` | `v2.0.10` | `b8cedc1a7a5e2916bbb65dc1d4b620729c261638` | 2026-09-19 | MIT | same pin as `tests/corpora/actions/SOURCES.md` |
| Cline CLI (installed) | `3.0.74` (`tests/e2e/.clients/cline`, git-ignored; `@cline/*` `0.2.0`) | `cli-v3.0.74` (annotated tag, dereferenced) | `071e1b25b48f9ef5dff7fc32085e6a16f02bf02e` | 2026-10-26 | Apache-2.0 | `cline/cline`, MCP code in `sdk/packages/core/src/extensions/mcp/` |
| Cline 4.x | `v4.1.27` (latest release on 2026-11-22) | `v4.1.27` | `8075d2e35cf5cad67c24f180c80a05d311b74a3e` | 2026-11-21 | Apache-2.0 | VS Code extension (`apps/vscode`); `v4.1.26` = `a459f1d04dea030833b558be645011ab739c463b` is PRD-021's pin and has a byte-identical `name-transform.ts` |

`where cline` finds nothing on `PATH`: the Cline CLI is the pinned local install.
OpenCode is the npm shim `opencode.cmd`; the runs used the real
`opencode.exe` under `node_modules/@opencode/cli/bin/`. The releases API lists
`v1.19.6` as OpenCode's latest while `v2.x` tags exist; every statement here is
pinned by tag, so that does not matter.

### The per-client record (answer to AC1, AC2, AC3)

| | OpenCode 2.3.2 | Cline CLI 3.0.74 | Cline 4.x (`v4.1.27`) |
|---|---|---|---|
| **Config file** | `mcp.servers.<name>` in `opencode.json[c]`, or `OPENCODE_CONFIG_CONTENT` (source: [config schema][oc-cfg], [docs][oc-docs]; observed via `OPENCODE_CONFIG_CONTENT`) | `<data dir>/settings/cline_mcp_settings.json`, or `CLINE_MCP_SETTINGS_PATH` (source: [paths][cl-paths]; observed with `--data-dir`) | `cline_mcp_settings.json` read by the extension (source: [schemas][cl4-schemas]) |
| **Remote entry** | `{"type": "remote", "url": ..., "headers": {...}, "oauth": false, "codemode": false}` (source: [RemoteConfig][oc-sch]). `enabled` does not exist: the key is `disabled` | `{"mcpServers": {"harness": {"type": "streamableHttp", "url": ..., "headers": {...}}}}` (observed; source: [loader][cl-loader]) | same shape; also `disabled`, `timeout` (seconds), `autoApprove` (source: [schemas][cl4-schemas]) |
| **Transport** | Streamable HTTP (SDK `StreamableHTTPClientTransport`, [client][oc-client]); no SSE fallback seen in the code opened | **`type` is mandatory.** Omitted, a URL entry is **SSE** (source: [loader][cl-loader]); observed: with `type` omitted the client sent only `GET /mcp` `Accept: text/event-stream` and never POSTed, so no tool appeared | Omitted `type` also defaults to `sse` (source: [schemas][cl4-schemas] `:116`). `streamableHttp` uses `StreamableHTTPClientTransport` ([McpHub][cl4-hub]) |
| **`initialize.protocolVersion` sent** | `2025-11-25` (observed). Default `protocol: "legacy"`; `auto` probes `2026-07-28` and falls back, `2026-07-28` pins it (source: [Protocol][oc-sch], [negotiation][oc-client-neg]). Not observed with `auto` | `2025-11-25` (observed). `2024-11-05` in `client.ts:49` is the stdio path only | `2025-11-25` expected (source: TS SDK `^1.29.0`); **not observed** (VS Code) |
| **SDK** | `@modelcontextprotocol/client` **2.4.0**, patched (`package.json:110`, `:177`); its `LATEST_PROTOCOL_VERSION` is `2025-11-25` and `DEFAULT_NEGOTIATED_PROTOCOL_VERSION` `2025-03-26` (read from the 2.4.0 tarball). STORY-001's "v1.29.x" guess does not hold for OpenCode | `@modelcontextprotocol/sdk` `^1.29.0` ([package.json][cl-pkg]); installed `1.32.2`: `LATEST_PROTOCOL_VERSION = 2025-11-25`, supported `2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05, 2024-10-07` (read from the install) | `^1.29.0` ([package.json][cl4-pkg]) |
| **`initialize.capabilities` sent** | `elicitation {form, url}` and `roots {}` (observed; source: [client][oc-client-caps]). Both are things the harness must never request back | `{}` (observed) | `{}` (source: [McpHub][cl4-hub] `:466-473`) |
| **`clientInfo`** | `opencode` / `2.3.2`; `User-Agent: opencode/latest/2.3.2/cli` (observed) | `@cline/core` / `0.0.0`; `User-Agent: Bun/1.4.2` (observed) | `Cline` / extension version (source) |
| **Static `Authorization`** | Sent on every request (observed). `requestInit.headers` is the configured map ([client][oc-client-url]) | Sent on every request (observed) | `requestInit.headers` ([McpHub][cl4-hub] `:619-625`) |
| **`Origin` sent?** | **No** (observed: the logged headers are `Accept`, `Authorization`, `Content-Type`, `User-Agent`, `mcp-protocol-version`, `mcp-session-id`) | **No** (observed, same set) | Not observed; source sets none (Node `fetch`). **Not verified** |
| **Other headers** | After `initialize` returns `Mcp-Session-Id: sess-1`, every later request echoes `mcp-session-id` and `mcp-protocol-version: 2025-11-25` (observed) | same (observed) | same SDK behaviour (source) |
| **After `initialized`** | `GET /mcp` `Accept: text/event-stream`, then `POST tools/list`. A `405` on the GET is accepted (observed) | same (observed) | rewrites a `404` on the GET into `405` ([McpHub][cl4-hub] `:607-618`) |
| **On `401`** | **No OAuth discovery.** First `POST initialize` got `401` with `WWW-Authenticate: Bearer realm="harness"`: no further request of any kind, no `/.well-known/*`, no retry within the run (observed, `once401` and `always401`, with and without `oauth: false`). Source: "A connection never starts a login" ([oauth.ts][oc-oauth] `:266-267`); with no stored credential the auth provider returns no token and a `401` ends in `needs_auth` (`:276`) | **No OAuth discovery** (observed, `once401` and `always401`: one `POST`, nothing else). Source: a connection omits the OAuth provider unless tokens are already stored, so the SDK reports `UnauthorizedError` at once ([client.ts][cl-client] `:793-803`); a `401` with a configured `Authorization` header reports "rejected its configured Authorization header" and is not marked as needing OAuth (`:837-841`, `:929`) | The extension **always** builds an OAuth provider for remote transports (`getOrCreateProvider`, [McpHub][cl4-hub] `:479-483`), so a `401` can start discovery in the SDK. `redirectToAuthorization` is a no-op signal ([McpOAuthManager][cl4-oauth] `:92`, `:155`). **Not observed**: assume it may probe `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`, and have the harness answer `404` there |
| **Model-facing name for server `harness`, tool id `postgres-staging__query`** | `harness_postgres-staging__query` (**observed** in the provider's `tools[]`, `codemode: false`) | `harness__postgres-staging__query` (**observed**) | `harness__postgres-staging__query` (source: [name-transform][cl4-name], same file and rule as 3.0.74) |
| **Rule** | `<server>_<tool>`: each part with every character outside `[a-zA-Z0-9_-]` replaced by `_` (one `_` per character). **No length cap, no truncation, no hash** (source: [`runtime.ts:289-294`][oc-runtime], [`tool/mcp.ts:23-24`][oc-tool-mcp]; observed: a 111-character name sent unchanged, `we.ird name` -> `harness_we_ird_name`) | `<server>__<tool>`; if that has a character outside `[a-zA-Z0-9_-]` or is over **64** characters: every run of invalid characters becomes one `_`, the result is cut to 55 characters and `_` + the first 8 hex of `sha1(raw)` is appended, 64 in all (source: [name-transform][cl374-name] `:20-35`; observed, vectors below) | identical to 3.0.74 (source, file compared byte for byte at both tags) |
| **Longest unchanged `<server>__<tool>`** | **no limit from OpenCode** (observed 111 chars; the cap belongs to the model provider, for example 64 at OpenAI, and OpenCode does not truncate: no cap in the code opened). The name is `harness_` + the id | **55 characters** for the id when the server is `harness` (observed: 55 unchanged, 56 hashed). Generally `64 - len(server) - 2` for the tool part | same as 3.0.74 |
| **MCP tools reach the model as** | direct tools only with `codemode: false`. The default is `true` (source: [`mcp-codemode-defaults.ts`][oc-defaults], [`tool/mcp.ts:57`][oc-tool-mcp]; observed: without the key, `tools[]` held `execute` and no `harness_*` entry) | direct tools | direct tools |
| **`tools/list` fields read** | `name` (a non-empty string), `title`, `description`, `inputSchema`, `outputSchema`, `annotations`, `execution`, `_meta`. A tool whose `inputSchema` is not an object, or whose `type` is not `"object"`, **is dropped** ([client][oc-client-tools] `:637-667`). **Only the first page**: `listTools` is called once and `nextCursor` is not followed (the cursor loop in the file is for `events/list`). Requires `capabilities.tools` (`advertised("tools")`) | `name`, `description`, `inputSchema`, `_meta` ([client.ts][cl-client] `:852-868`). **No `title`, `outputSchema` or `annotations` read.** No cursor handling | adds `annotations` ([client][cl4-client] `:372-402`); still no `title`/`outputSchema`; no cursor handling |
| **`initialize` fields read** | `protocolVersion` (negotiated), `capabilities` (`tools`, `prompts`, `resources`, their `listChanged`), `serverInfo.title` (display), **`instructions`** (trimmed, injected into the model context as `<mcp_instructions>`: [instructions.ts][oc-instr]) ([client][oc-client] `:549-558`) | the SDK's `Client` negotiates; the code opened reads **no `instructions`, no `serverInfo`** (grep of `client.ts`). **Not verified** in the bundled binary | same as 3.0.74 (source) |

### Redacted excerpts (observed)

OpenCode 2.3.2, `mcp.servers.harness = {type: "remote", url: "http://127.0.0.1:<port>/mcp", headers: {Authorization: "Bearer test-token"}, codemode: false}`, listener answering normally:

```
POST /mcp  Accept: application/json, text/event-stream  Authorization: Bearer test-token  User-Agent: opencode/latest/2.3.2/cli   (no Origin)
  {"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{"elicitation":{"form":{},"url":{}},"roots":{}},"clientInfo":{"name":"opencode","version":"2.3.2"}},"jsonrpc":"2.0","id":0}
POST /mcp  ... mcp-protocol-version: 2025-11-25  mcp-session-id: sess-1    {"jsonrpc":"2.0","method":"notifications/initialized"}
GET  /mcp  Accept: text/event-stream  mcp-protocol-version: 2025-11-25  mcp-session-id: sess-1
POST /mcp  ... {"method":"tools/list","jsonrpc":"2.0","id":1}
provider request tools[] (abridged): edit, glob, grep, harness_postgres-staging__query, question, read, shell, skill, subagent, webfetch, websearch, write, execute
```

Cline CLI 3.0.74, same listener, `type: "streamableHttp"`:

```
POST /mcp  Accept: application/json, text/event-stream  Authorization: Bearer test-token  User-Agent: Bun/1.4.2   (no Origin)
  {"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"@cline/core","version":"0.0.0"}},"jsonrpc":"2.0","id":0}
POST /mcp  ... notifications/initialized   GET /mcp (event-stream)   POST /mcp tools/list
provider request tools[]: read_files, run_commands, editor, submit_and_exit, harness__postgres-staging__query
```

`401` runs: a single `POST /mcp initialize` and nothing after it for both clients.

Cline name vectors (observed in `tools[]`, and equal to a Python replica of the rule), server `harness`:

| Tool part sent by the listener | Model-facing name |
|---|---|
| `postgres-staging__query` | `harness__postgres-staging__query` |
| 55 x `d` | `harness__` + 55 x `d` (64 characters, unchanged) |
| 56 x `e` | `harness__` + 46 x `e` + `_159dbc35` (64 characters) |
| `postgres-staging__` + 85 x `a` | `harness__postgres-staging__aaaaaaaaaaaaaaaaaaaaaaaaaaaa_5cc0491b` |
| `we.ird name` | `harness__we_ird_name_95abd58c` |

### Verdict on `v1_aliases.prefixes: ["harness_", "harness__"]` (answer to AC3)

**Right as far as it goes, with three conditions.**

1. **Both prefixes are real and both are needed**, for a server named `harness`
   in the client's own config: OpenCode sends `harness_<id>`, Cline sends
   `harness__<id>`, where `<id>` is the harness tool id `<server>__<tool>`.
   Both strip to `<id>` exactly. The prefix is the client-side server key:
   the client docs (STORY-020) must say "name the server `harness`", and an
   operator who names it otherwise needs a different `prefixes` list.
2. **The overlap resolves, no ambiguity.** For a Cline name `harness__x__y` the
   `harness_` prefix leaves `_x__y`. Server ids match `[a-z0-9][a-z0-9-]{0,31}`,
   so a remainder that starts with `_` is not a `<server>__<tool>` and does not
   resolve; only `harness__` does. For an OpenCode name `harness_x__y`, the
   `harness__` prefix does not match (third character `x`). Split the remainder
   at the first `__`, because server ids hold no underscore.
3. **Cline hashes long names, so a prefix strip is not enough.** When the
   `<id>` is over 55 characters (with `harness`), or has a character outside
   `[a-zA-Z0-9_-]` (for example an upstream tool named `get.item`), Cline sends
   `<sanitized[:55]>_<sha1(raw)[:8]>`, which no prefix strip can undo. STORY-016
   must also keep, per request, a reverse map from
   `defaultMcpToolNameTransform("harness", id)` to `id` for every tool the
   caller can see, and match on it before the prefix rule. OpenCode never
   hashes, but its sanitizing is per character (`we.ird name` ->
   `we_ird_name`), so a reverse map by the same rule covers it too. Limits for
   STORY-016's tests: Cline 55 characters unchanged and 56 hashed (vectors
   above); OpenCode unchanged at 111.

Neither client sends a name with a prefix other than the two listed when the
server key is `harness`, and neither uses the 3.x `0mcp0` scheme
(`tests/corpora/actions/SOURCES.md:222`): that belongs to the old extension
(`apps/vscode/src/core/prompts/system-prompt/registry/ClineToolSet.ts`), and Cline 3.0.74 sent `harness__...`.

### Facts the northbound half needs (feeds STORY-011, STORY-020)

- **Legacy handshake only, by default.** Both installed clients open with
  `initialize` at `2025-11-25` and never send `server/discover` (observed).
  OpenCode can be set to `protocol: "auto"` (probes `2026-07-28`, falls back to
  legacy) or pinned; that is opt-in and not observed.
- **Static bearer works, no OAuth dance** (observed both). A harness that
  answers `401` to a bad key gets no discovery traffic from these two; answer
  `404` on `/.well-known/oauth-*` anyway for the Cline 4.x extension (not
  observed).
- **No `Origin`** from either CLI. Reject a present, foreign `Origin` (spec) and
  accept an absent one.
- **Pagination is not followed**: return every visible tool in one `tools/list`
  page, no `nextCursor`.
- **`inputSchema.type` must be `"object"`** or OpenCode drops the tool silently.
- **Declare `capabilities.tools`**: OpenCode lists tools only when advertised.
- **`instructions` is consumed by OpenCode** (injected into the prompt) and not
  by Cline 3.0.74: keep it short and never put a secret or a URL in it.
- **`GET /mcp` after `initialized`**: both open it; `405` is accepted by both
  (observed) so the harness need not stream.
- **OpenCode adds `?codemode=false` to a non-loopback URL** when the server has
  no `codemode` key (source: [client][oc-client-url] `:481-484`); if that
  request fails with `400`/`404` it retries the configured URL. Loopback hosts
  are exempt (observed: path stayed `/mcp`). `/mcp` should ignore unknown query
  parameters rather than answer `400`.
- **Declared client capabilities** (`elicitation`, `roots`) are a client-side
  fact: the harness declares none and sends no server-to-client request, so
  these are never used.

### OpenCode 2.0.10 against 2.3.2 (cheap check)

Same naming rule at `v2.0.10`
([`tool/mcp.ts:16-17`][oc2010-tool-mcp]: `sanitize(server) + "_" + sanitize(tool)`),
same `mcp.servers.<name>` config with `type`, `url`, `headers`, `oauth`,
`codemode` and `protocol` keys in `packages/schema/src/mcp.ts` at the older tag.
The SDK there is `@modelcontextprotocol/client` `2.0.0` (`packages/core/package.json:113`),
not 2.4.0. Behaviour of the `2.0.10` binary on the wire was **not observed**; the
2.3.2 results are the target.

### Not verified here

- Cline 4.x (the VS Code extension): not run (needs the GUI). Its `protocolVersion`,
  `Origin` and whether a `401` starts discovery are from source or inference only.
  Safe defaults are stated above.
- Any run with `opencode mcp ...` subcommands: not run (they start OpenCode's
  background service); `run --standalone` was used.
- OpenCode with `protocol: "auto"` or `"2026-07-28"`, and `oauth` with a stored
  credential: not run.
- Behaviour after a `401` beyond a few seconds, and `DELETE` on close (the runs
  ended by killing the process tree).
- Whether Cline 3.0.74's bundled binary reads `instructions` or `serverInfo`: the
  source at the tag shows no read; the minified binary was not searched for it.
- The `0mcp0` scheme in the 3.x VS Code extension: not re-checked.

## Servers

### GitHub MCP server (answer to AC4)

`github/github-mcp-server` `v2.2.0` (MIT), commit
`67d4dc489700ec955ad255d098396dd86c729523` (2026-11-16, resolved from the
lightweight tag; the tags `v2.1.0` and `v2.0.3` also exist). The input schemas
below are read from the generated snapshots in `pkg/github/__toolsnaps__/`
([create_branch][gh-snap-branch], [push_files][gh-snap-push],
[create_pull_request][gh-snap-pr]) and the tool definitions in
[`repositories.go`][gh-repos] and [`pullrequests.go`][gh-prs]. Static analysis
only: no server was run and no GitHub call was made.

| Tool | Toolset | `required` | Arguments (type) | Hints |
|---|---|---|---|---|
| `create_branch` | `repos` ([`repositories.go:1531-1537`][gh-repos]) | `owner`, `repo`, `branch` | `owner` string, `repo` string, `branch` string, `from_branch` string (optional) | `readOnlyHint: false`, `idempotentHint: false` |
| `push_files` | `repos` ([`repositories.go:1641-1647`][gh-repos]) | `owner`, `repo`, `branch`, `files`, `message` | `owner`, `repo`, `branch`, `message` strings; **`files`: array of objects `{path: string, content: string}`, both required, no other property** (`additionalProperties: false`) | `readOnlyHint: false`, `idempotentHint: false` |
| `create_pull_request` | `pull_requests` ([`pullrequests.go:702-704`][gh-prs]) | `owner`, `repo`, `title`, `head`, `base` | `owner`, `repo`, `title`, `head`, `base`, `body` strings; `draft` boolean, `maintainer_can_modify` boolean, `reviewers` array of strings | `readOnlyHint: false`, `idempotentHint: false` |

- **No name change** against the PRD text: the three names are as the PRD says.
  The path argument is `files[].path` (with `files[].content`), as AC4 expects.
- **Gating**: write tools belong to the `repos` and `pull_requests` toolsets and
  are skipped under `--read-only`, which takes priority over an explicit tool
  list ([README][gh-readme] `:497`: "Read-only mode takes priority: write tools are skipped if `--read-only` is set, even if explicitly requested via `--tools`"); both toolsets are `Default: true` ([`tools.go:40-61`][gh-tools]). A harness that
  lists a tool the upstream gates out sees no entry for it in `tools/list`.
- **Schema features a passthrough must preserve**: `owner` and `repo` in
  `create_branch` and `push_files` carry an `x-mcp-header` extension keyword
  (`"x-mcp-header": "owner"`, `"repo"`) in the snapshots, tied to the
  `2026-07-28` `Mcp-Param-{Name}` header mirroring; `create_pull_request` has
  `_meta.ui.resourceUri` and a `oneOf` `outputSchema`; `create_branch` and
  `push_files` carry `icons` as `data:` URIs (large). The keyword is not in the
  Go sources opened (it is added when the schema is produced); it is only seen
  in the snapshots. **Not verified** how the live `tools/list` serialises these.
  Safe default for STORY-011's `tools/list`: forward `inputSchema` verbatim and
  drop `icons` and `_meta`, since no client above reads them.
- No engine decision is made here: `push_files` names several files per call, so
  the PRD's `tool.opaque` default for an MCP call stands unless a later story
  maps it.

[oc-sch]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/schema/src/mcp.ts#L20-L23
[oc-cfg]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/schema/src/config/mcp.ts#L19-L22
[oc-docs]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/services/site/src/docs/content/mcp-servers.mdx
[oc-client]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/mcp/client.ts#L549-L558
[oc-client-url]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/mcp/client.ts#L481-L489
[oc-client-caps]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/mcp/client.ts#L356-L362
[oc-client-tools]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/mcp/client.ts#L625-L668
[oc-client-neg]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/mcp/client.ts#L808-L813
[oc-oauth]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/mcp/oauth.ts#L262-L297
[oc-runtime]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/tool/runtime.ts#L289-L294
[oc-tool-mcp]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/tool/mcp.ts#L20-L57
[oc-defaults]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/plugin/mcp-codemode-defaults.ts
[oc-instr]: https://github.com/anomalyco/opencode/blob/c0ad18b402eb2827fc1ee71c171b1177b3fc02d1/packages/core/src/mcp/instructions.ts#L8-L25
[oc2010-tool-mcp]: https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/mcp.ts#L16-L17
[cl-paths]: https://github.com/cline/cline/blob/071e1b25b48f9ef5dff7fc32085e6a16f02bf02e/sdk/packages/shared/src/storage/paths.ts#L447-L453
[cl-loader]: https://github.com/cline/cline/blob/071e1b25b48f9ef5dff7fc32085e6a16f02bf02e/sdk/packages/core/src/extensions/mcp/config-loader.ts#L166-L210
[cl-client]: https://github.com/cline/cline/blob/071e1b25b48f9ef5dff7fc32085e6a16f02bf02e/sdk/packages/core/src/extensions/mcp/client.ts#L793-L868
[cl-pkg]: https://github.com/cline/cline/blob/071e1b25b48f9ef5dff7fc32085e6a16f02bf02e/sdk/packages/core/package.json#L59
[cl374-name]: https://github.com/cline/cline/blob/071e1b25b48f9ef5dff7fc32085e6a16f02bf02e/sdk/packages/core/src/extensions/mcp/name-transform.ts#L20-L35
[cl4-name]: https://github.com/cline/cline/blob/8075d2e35cf5cad67c24f180c80a05d311b74a3e/sdk/packages/core/src/extensions/mcp/name-transform.ts#L20-L35
[cl4-client]: https://github.com/cline/cline/blob/8075d2e35cf5cad67c24f180c80a05d311b74a3e/sdk/packages/core/src/extensions/mcp/client.ts#L372-L402
[cl4-pkg]: https://github.com/cline/cline/blob/8075d2e35cf5cad67c24f180c80a05d311b74a3e/sdk/packages/core/package.json#L59
[cl4-hub]: https://github.com/cline/cline/blob/8075d2e35cf5cad67c24f180c80a05d311b74a3e/apps/vscode/src/services/mcp/McpHub.ts#L466-L625
[cl4-oauth]: https://github.com/cline/cline/blob/8075d2e35cf5cad67c24f180c80a05d311b74a3e/apps/vscode/src/services/mcp/McpOAuthManager.ts#L92-L155
[cl4-schemas]: https://github.com/cline/cline/blob/8075d2e35cf5cad67c24f180c80a05d311b74a3e/apps/vscode/src/services/mcp/schemas.ts#L116-L152
[gh-repos]: https://github.com/github/github-mcp-server/blob/67d4dc489700ec955ad255d098396dd86c729523/pkg/github/repositories.go#L1531-L1647
[gh-prs]: https://github.com/github/github-mcp-server/blob/67d4dc489700ec955ad255d098396dd86c729523/pkg/github/pullrequests.go#L702-L704
[gh-readme]: https://github.com/github/github-mcp-server/blob/67d4dc489700ec955ad255d098396dd86c729523/README.md#L497
[gh-tools]: https://github.com/github/github-mcp-server/blob/67d4dc489700ec955ad255d098396dd86c729523/pkg/github/tools.go#L40-L61
[gh-snap-branch]: https://github.com/github/github-mcp-server/blob/67d4dc489700ec955ad255d098396dd86c729523/pkg/github/__toolsnaps__/create_branch.snap
[gh-snap-push]: https://github.com/github/github-mcp-server/blob/67d4dc489700ec955ad255d098396dd86c729523/pkg/github/__toolsnaps__/push_files.snap
[gh-snap-pr]: https://github.com/github/github-mcp-server/blob/67d4dc489700ec955ad255d098396dd86c729523/pkg/github/__toolsnaps__/create_pull_request.snap
