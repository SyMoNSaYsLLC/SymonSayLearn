# symoneural-com — inference through a browser

**State: partial.** The site builds, serves, and reads live data from the gateway. Two of
seven surfaces are real; the rest are honest placeholders. Nothing is public yet.

## What is true, and how it was proved

| Claim | Evidence |
|---|---|
| The built site serves | `node server.js` from the staged standalone bundle, `127.0.0.1:3000`, every route 200 |
| The overview reads live state | renders gateway "answering", credential "loaded" by fingerprint, chat unit "ready" |
| The models surface reads the live registry | renders all three models with tier, default flag and context window, fetched from `GET /v1/models` |
| The credential never reaches the browser | read server-side only; the page renders a 16-character fingerprint and never the value |

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
| Chat, Code, Cowork, Rack, Settings | placeholders that say so rather than rendering an empty frame |

## Next

1. **Chat.** The one surface that makes the site useful. It needs a streaming route on the
   server that proxies `POST /v1/messages` with the credential attached, and a client that
   renders the event stream. The dialect's event order is already verified by the suite.
2. **Rack.** Needs the control plane on `127.0.0.1:8800`, which is protected and currently not
   listening. The surface will honestly show it down until something brings it up.
3. **Public name and certificate.** Not started. This is where the path stops being local.

## Blocked

- **A public hostname and a certificate** need a DNS change and an account action. Nothing on
  this host currently terminates TLS or proxies.
- **The rack surface** needs the control plane, which is read-only and demo-critical, so it is
  brought up by whatever normally supervises it and not by this work.
