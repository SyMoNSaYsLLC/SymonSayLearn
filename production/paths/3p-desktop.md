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
| All four models are offered | `Model discovery: 4 found in 20ms; picker = 4 (inferenceModels)` |
| Effort levels are available | an explicit model list carries a per-model ceiling and a display label, neither of which discovery can express |
| A remote Code session is permitted | `session placement at launch: local-only: device allowed, SSH host allowed` |
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

- Tool calling is **built and verified against the real checkpoint**, in the runtime rather
  than the client; see [own-runtime.md](own-runtime.md). What remains for this path is
  exercising it through the client itself, which needs the runtime serving rather than the
  stand-in engine.
- The Code surface over SSH. The host entry exists; the allowlist is unset.
- Drive a tool from the client. The runtime can do it; what remains is exercising it through
  this client, which wants our own runtime serving rather than the stand-in engine.
- Open a Code session on the allowed host and confirm it reaches the estate.

## Blocked

Nothing.
