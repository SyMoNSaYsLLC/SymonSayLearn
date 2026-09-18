# symoneural-com — inference through a browser

**State: partial.** The site builds, serves, and holds a real conversation with our own
models. Six of seven surfaces are real; the rest are honest placeholders. Nothing is
public yet.

## What is true, and how it was proved

| Claim | Evidence |
|---|---|
| The built site serves | `node server.js` from the staged standalone bundle, `127.0.0.1:3000`, every route 200 |
| The overview reads live state | renders gateway "answering", credential "loaded" by fingerprint, chat unit "ready" |
| The models surface reads the live registry | renders all three models with tier, default flag and context window, fetched from `GET /v1/models` |
| The credential never reaches the browser | read server-side only; the page renders a 16-character fingerprint and never the value |
| Chat answers through the site | `POST /api/chat` streamed 60 events in correct order and returned "Paris is the capital of France." with the reasoning block kept separate |
| A malformed request is refused | `{"messages":[]}` returns the dialect envelope `invalid_request_error: model is required` |
| It installs from a published release and runs | v1.2.0: checksums verify, the unit installs, its launcher starts it, and it serves every surface |

## Architecture, and the one rule that shapes it

The browser never holds the credential and never talks to the gateway. Every authenticated
call is made by the server process, which reads the same 0600 file the gateway reads. This is
why the surfaces are server-rendered on demand rather than static: a static page cannot hold
a live answer, and a client-side fetch would need a secret in the browser.

## Surfaces

| Surface | State |
|---|---|
| Overview | real — live probes of gateway, credential, chat unit, control plane |
| Models | real — the live registry, including whether each row survives a client's own filter |
| Chat, Code, Cowork | real — one conversation component, each surface preferring its own tier, streamed answers with reasoning folded away |
| Settings | real — the values this process is actually using, with credentials as a fingerprint |
| Rack | placeholder; it needs the control plane, which is protected and not listening |

## Next

1. **Rack.** Needs the control plane on `127.0.0.1:8800`, which is protected and currently not
   listening. The surface will honestly show it down until something brings it up.
2. **Public name and certificate.** Not started. This is where the path stops being local.
3. **Conversation persistence.** A reload loses the thread; there is no store behind it yet.

## Recorded roadblock

The `server-only` package would make "this module is server-side" a build error. It is not in
the dependency set and the package manager cannot reach a registry from this host, so the
credential module throws at runtime instead. That is weaker — it fires on first use rather
than at compile time — and it is written into the file rather than left silent.

## Blocked

- **A public hostname and a certificate** need a DNS change and an account action. Nothing on
  this host currently terminates TLS or proxies.
- **The rack surface** needs the control plane, which is read-only and demo-critical, so it is
  brought up by whatever normally supervises it and not by this work.
