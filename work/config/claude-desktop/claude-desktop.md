# claude-desktop

Configuration for the client that calls this estate's gateway. Tracked here so the
deployment is a file under version control rather than a set of hand-set switches
that only exist in one person's application window, and so a future first-party
interface can read the same declaration instead of re-deriving it.

## Files

| File | Role |
|---|---|
| `symonAI.json` | the configuration. **No credential.** |
| `apply-symonAI-config.sh` | installs it into the profile; refuses while the app runs |
| `claude-desktop-settings.md` | every setting, what to set it to, and why |
| `ssh-code-surface.md` | the Code surface's SSH values, with the live verification |
| `symonAI.live-export.json` | what the profile held before this directory existed |

## Interfaces

| Direction | What |
|---|---|
| Writes | `~/.config/Claude-3p/configLibrary/symonAI.json` and `_meta.json` |
| Backs up | `~/.config/Claude-3p/configLibrary.bak-<timestamp>` before any write |
| Points the client at | `http://localhost:9001` — the gateway in `work/runtimes/api/app/symoneural_api/` |
| Reads credential from | nowhere. See below. |

## The credential is not in this directory

`inferenceGatewayApiKey` is deliberately absent from `symonAI.json`. It lives in two
places, neither of them tracked:

1. the application window, stored by the app with `redact: drop`
2. `~/.config/symoneural/gateway-9001.key`, mode 0600, which the gateway reads

The installer carries an existing credential across between entries by reading and
rewriting it without printing it, so applying a new configuration does not require
re-entering the key. Nothing here ever displays a secret; `symoneural-secrets status`
and a sha256 prefix are how a credential is identified.

## Why the application must be quit first

The app owns `~/.config/Claude-3p/configLibrary/` and rewrites both the entry file and
`_meta.json` when it saves. Editing them under a live app means the in-memory copy
wins on the next write and the change vanishes with no error anywhere. The installer
checks `pgrep -x claude-desktop` and refuses rather than producing that outcome.

## The one setting that everything else depends on

`modelDiscoveryEnabled: true` with an empty Models list. This is not a preference.

Measured from the installed bundle (`/usr/lib/claude-desktop/resources/app.asar`,
2.2553.0), a discovered model row survives only if its id matches an allow-pattern or
the row declares `anthropic_family_tier`:

```js
Nxe = /...|gpt|...|openai|.../        // hard blocklist
qo(id) = Nxe.test(id) ? false : Ko.test(id) || Mxe.some(m => id.includes(m))
```

No `symon-*` id matches an allow-pattern, so the tier field the gateway emits is what
makes a first-party model selectable at all. Typed entries in the Models list go
through a different validator that cannot carry that field and drops anything it
judges "not an Anthropic model", so typing the model names in is the one way to break
this. Leave the list empty and let discovery do it.

## Onward

The gateway this configuration points at is documented in
`work/runtimes/api/app/symoneural_api/symoneural_api.md`. That document holds the
endpoint register, the credential model and the proof that promoted each route.
