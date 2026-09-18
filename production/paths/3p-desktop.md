# 3p-desktop — inference through a reference client on this host

**State: working.** Verified 2026-09-18. A client in third-party mode reaches our gateway,
lists three models and completes a chat. The configuration is a user configuration, editable
in the application, not a locked policy.

## What is true, and how it was proved

| Claim | Evidence |
|---|---|
| The client runs in third-party mode | every process carries `--user-data-dir=/home/google/.config/Claude-3p` |
| It reaches our gateway | its log records `inference apiHost=http://localhost:9001` |
| It obtains the credential without one being stored | `helper ok (elapsed=11ms stdoutBytes=64)` |
| Models are offered | `Model discovery: 3 found in 27ms; picker = 3 (discovery)`; a fourth tier has since been added |
| The quick tier is no longer empty | `symon-haiku` claims the haiku tier, so the per-tier default a client sets for its own background work resolves to one of ours instead of an empty string |
| A deliberation request no longer reaches the engine | a message carrying a `thinking` block returns `end_turn` with text, where the field was previously forwarded to an engine that never declared it |
| A request completes end to end | 41-check suite, `work/tools/verify-3p-path.sh`, all passing |

## The three faults that had to be fixed, and why each was invisible

1. **No configuration source existed.** Third-party mode is gated on a configuration that
   carries inference settings. With none present the answer is decided before the persisted
   mode key is ever read, so setting that key could not have worked.
2. **Our installer wrote an entry the client could not load.** It named the entry `symonAI`,
   but an entry loads only when its id is a 36-character identifier. The entry was written
   and applied without complaint and then ignored, so a day of configuration had no effect.
3. **Our model ids were discovered and then dropped.** A client keeps a row only when the id
   names a tier or contains one of a small set of tokens. `symon-chat` matched none, so the
   picker stayed empty while every request through the same gateway succeeded.

Fault 3 is the one worth remembering: **the request path working is not evidence that a
client can use it.** Nothing in a successful completion reveals an empty picker.

## Rejected, and why it is recorded rather than forgotten

A configuration placed under `/etc/claude-desktop/` also turns the mode on. It marks the
deployment as organisation-managed and makes every field read-only in the application, which
is wrong for a single operator who needs to change settings. Quarantined, not deleted.

## Next

- Tool calling. The channels prompt style cannot yet emit a tool-use block, so the model
  cannot drive tools from this client. Tracked in [own-runtime.md](own-runtime.md), because
  the change is in the runtime rather than the client.
- The Code surface over SSH. The host entry exists; the allowlist is unset.
- Effort levels. Measured: effort is entirely client configuration and nothing the gateway
  emits can turn it on. It needs an explicit model list in the client's own configuration,
  which also lets each entry carry a nicer label than its wire id.
- The Code surface over SSH. Measured: the host resolves, the daemon listens, and the remote
  engine is already installed. Three configuration keys stand between here and a session.

## Blocked

Nothing.
