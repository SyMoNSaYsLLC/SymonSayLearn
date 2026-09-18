# paths — the three inference routes, tracked separately

Three ways a person reaches SyMoNeuRaL's own models. They share one gateway and one
engine and nothing else, so they are tracked apart: a change that unblocks one of them
routinely does nothing for the other two, and collapsing them into a single status has
twice hidden the fact that only one was actually working.

| Path | Document | Who it serves | State on 2026-09-18 |
|---|---|---|---|
| Desktop third-party inference | [3p-desktop.md](3p-desktop.md) | a reference client on this host | **working** — chat answers, three models offered |
| symoneural.com | [symoneural-com.md](symoneural-com.md) | a browser, eventually off this host | **partial** — served locally, overview live, surfaces unbuilt |
| Our own runtime | [own-runtime.md](own-runtime.md) | every path above, underneath | **substituted** — an acquired engine stands in |

## What they share

One gateway on `127.0.0.1:9001` speaking the Messages dialect, and one chat unit on
`127.0.0.1:8802` behind it. Every path talks to the gateway and none talks to the engine
directly, which is what lets the engine be replaced without any client noticing. The
credential is one file, mode 0600, read by the gateway and by anything acting on the
operator's behalf — never by a browser and never by an agent whose task does not need it.

## What they do not share

The desktop path needs model ids that a client's own filter will accept. The web path
needs a process serving HTTP and, eventually, a public name and a certificate. The engine
path needs neither of those and is blocked on something entirely different. Progress on
one is not evidence about the others.

Onward: each document states its own state, what is verified, what is next, and what is
blocked and on whom.
