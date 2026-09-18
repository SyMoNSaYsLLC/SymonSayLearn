# symoneural_api

The estate's control plane and its client-facing dialect. Two **separate processes**
are built from this one package, and confusing them is the mistake this document
exists to prevent.

| Process | Entry point | Binds | Serves | Status |
|---|---|---|---|---|
| Control plane | `symoneural_api.main:app` | `127.0.0.1:8800` | `/api/*` only | pre-existing, untouched |
| Dialect gateway | `symoneural_api.gateway:app` | `127.0.0.1:9001` | root probes + `/v1/*` | added 2026-09-18 |

`main.py` was not modified. R14 protects `127.0.0.1:8800` as read-only and
demo-critical, so the dialect was added as its own application object with its own
entry point rather than as new routes on the existing one. The two share `units.py`,
`routeclass.py` and `gpulock.py`; they share no route.

---

## 1. Endpoint register — the dialect gateway, port 9001

This is the complete list. Anything not in this table returns `404` in the dialect's
error envelope.

| Method | Path | Auth | Answers from | State |
|---|---|---|---|---|
| GET | `/health` | none | gateway process | see §5 |
| GET | `/ready` | credential | live probe of the chat unit | see §5 |
| GET | `/version` | credential | gateway + registry + engine report | see §5 |
| GET | `/v1/models` | credential | `models.REGISTRY` | see §5 |
| GET | `/v1/models/{model_id}` | credential | `models.REGISTRY` | see §5 |
| POST | `/v1/messages` | credential | chat unit, streaming and not | see §5 |
| POST | `/v1/messages/count_tokens` | credential | chat unit tokenizer | see §5 |

`/health` is the only unauthenticated route. It must answer while every unit is off
and while the gateway itself is unconfigured, because a probe that needs a working
system to report that the system is broken is not a probe.

### Credential

One key, read on every request from a file the operator provisions:

```
~/.config/symoneural/gateway-9001.key          mode 0600, overridable by SYM_GW_KEY_FILE
```

Both header spellings the dialect permits are accepted, because which one a client
sends is the client's choice:

```
Authorization: Bearer <key>
x-api-key: <key>
```

Compared with `hmac.compare_digest`. Never logged, never echoed, never included in an
error message. Read per request rather than cached, so a rotation takes effect on the
next request instead of the next restart.

**Unconfigured fails closed.** With no key file, every authenticated route answers
`500 api_error` naming the missing path. It does not fall back to open.

### Error envelope

Every failure, including `404` and auth failures, uses the dialect's shape:

```json
{"type": "error", "error": {"type": "authentication_error", "message": "..."}}
```

never FastAPI's `{"detail": ...}`. A client that pattern-matches the envelope to
decide whether a failure is retryable gets the wrong answer from `detail`, and the
failure then looks like a model problem instead of a gateway one.

Type to status: `invalid_request_error` 400, `authentication_error` 401,
`permission_error` 403, `not_found_error` 404, `request_too_large` 413,
`rate_limit_error` 429, `api_error` 500, `overloaded_error` 529.

### Request identity

Every response carries `x-request-id`. An inbound `x-request-id` is honoured and
echoed; otherwise one is minted before anything can fail, so a rejection carries one
too.

---

## 2. What the gateway adds that the engine cannot

The engine already speaks `POST /v1/messages` and `POST /v1/messages/count_tokens`,
so the gateway forwards those rather than re-encoding them. Re-deriving a wire format
the engine already emits is a second implementation of one spec, and the two drift.

The gateway exists for what the engine cannot do:

1. **`GET /v1/models` in the shape a client will accept.** This is the load-bearing
   one. Measured from Claude Desktop 2.2553.0 (`resources/app.asar`), a discovered
   row survives only if `qo(id)` passes **or** the row declares
   `anthropic_family_tier`:

   ```js
   Wo   = ["sonnet","opus","haiku","fable","mythos"]
   Ko   = /^(sonnet|opus|haiku|fable|mythos)(-[\d.]+)?$/
   Mxe  = ["claude", ...Wo, "anthropic"]
   Nxe  = /...|gpt|...|openai|.../         // hard blocklist
   qo(id) = Nxe.test(id) ? false : Ko.test(id) || Mxe.some(m => id.includes(m))
   ```

   No `symon-*` id matches an allow-pattern, so without the tier field every row is
   dropped and the picker comes back empty. The upstream checkpoint name is worse
   than dropped: `gpt` and `openai` are both blocklist entries, so the model can
   **never** be offered under it. An engine emitting plain OpenAI-shaped model rows
   cannot satisfy this; a first-party gateway is not a preference here, it is the
   only way a Symon-branded model is selectable.

2. **The credential.** The chat unit binds loopback and carries no key. One trust
   boundary, one secret.

3. **A closed public namespace.** An unknown model is refused by name rather than
   forwarded. The engine might answer to a name this estate never published, and
   forwarding would make that name live without it ever being registered.

4. **The public name on the way back.** The response `model` field is rewritten to
   the id the caller asked for, so the checkpoint name does not leak through a field
   every client logs.

---

## 3. The three cards

`models.py` registers one card per client surface. They are branches of one dialect,
not three engines.

| id | Display | Tier | Surface | Worker |
|---|---|---|---|---|
| `symon-chat` | Symon Chat | sonnet | Chat | `chat` unit |
| `symon-coder` | Symon Coder | opus | Code | `chat` unit |
| `symon-work` | Symon Work | fable | Cowork | `chat` unit |

All three resolve to the same unit and the same weights today, and
`GET /v1/models/{id}` says so in `x-symoneural.shares_weights_with` rather than
leaving it to be inferred from three similar rows. `worker_unit` and `worker_model`
are per-card so one can diverge later without re-architecting.

The three tiers are deliberately different. The tier doubles as the selector a client
uses when it asks for a model by tier rather than by id, so two cards sharing one
tier would be indistinguishable. The tier is a wire field, not a claim of equivalence
to anyone else's model.

Per-card sampling defaults fill only what the caller left unset. A client that sets
`temperature` has made a decision, and overriding it would be the gateway quietly
disagreeing with the caller.

---

## 4. Files

| File | Role |
|---|---|
| `gateway.py` | the 9001 process: app, credential, root probes, entry point |
| `dialect.py` | the `/v1` router and the error envelope |
| `models.py` | the model catalogue and per-card sampling |
| `worker.py` | the one client to the chat unit |
| `endpoints.py` | the frozen route register; states measured against disk |
| `units.py` | the rack registry; `chat` is 8802 |
| `routeclass.py` | the authorisation model for `/api/*` |
| `gpulock.py` | single-card arbitration |
| `main.py` | the 8800 control plane. **Not modified.** |

Upstream of here: `work/runtimes/llm/hostrun/` starts the chat unit this gateway
calls. Downstream: `work/config/claude-desktop/` configures the client that calls
this gateway.

---

## 5. State — BUILT, measured 2026-09-18

Endpoint states are measured against disk and against a consumer having exercised
them, never against intent. All seven rows are BUILT. The evidence, each from the
command's own output:

| Check | Result |
|---|---|
| `GET /health`, no credential | `200 {"status":"ok"}` with `x-request-id` |
| `GET /v1/models`, wrong credential | `401 authentication_error` |
| `GET /v1/models?limit=1000`, `x-api-key` | `200`, three rows, each carrying `anthropic_family_tier` |
| `GET /v1/models/symon-coder` | `200` with `x-symoneural` provenance |
| `GET /v1/nope` | `404 not_found_error` in the dialect envelope |
| `POST /v1/messages` model `gpt-oss-20b` | `404`, refused by name |
| **`POST /v1/messages`, the client probe shape** | **`200` in 0.365 s, `content` an array, `model` returned as `symon-chat`** |
| `GET /ready` | `200 {"status":"ready"}` naming all three models |

The last row of that table is the same request the client's Test button sends, so
the contract is exercised rather than asserted.

**What is NOT proven.** Streaming was proven against the chat unit directly, not yet
through the gateway's relay path. The client has not yet run its own Test, because
that needs the operator's credential; the gateway on 9001 is deliberately
unconfigured and answers every authenticated route with `500 api_error` naming the
missing key file until it is provisioned. The proof above ran on a spare port against
a public test fixture credential, the literal string `symon-gateway-test-fixture`,
which has zero entropy, is not a secret, and was removed afterwards.

`endpoints.py` is the machine-readable copy of this table and was updated in the same
change. Its validators pass: no duplicate paths, no unassigned units, no unknown
units.

---

## 6. The proof that promotes a row

The gateway is done when the client's own probe passes, not when the code is written.
That probe is, measured from the app bundle:

```
POST http://localhost:9001/v1/messages
authorization: Bearer <key>
anthropic-version: 2023-06-01
content-type: application/json

{"model":"symon-chat","max_tokens":1,"messages":[{"role":"user","content":"."}]}
```

and it requires a 2xx JSON body whose `content` is an **array**. It is a single
non-streaming round trip; serving only SSE fails it. Discovery runs first, so
`GET /v1/models?limit=1000` must return at least one row that survives the filter in
§2 before the message probe is even attempted.

Reproduce it with curl before anyone presses Test in the client.
