# SymonSayLearn

**SyMoNeuRaL's own inference runtimes — text, image, and the control plane that arbitrates
them — built from pristine upstream source on one machine, behind one API.**

The runtimes are the product. Nothing here forwards a request to a hosted model. Every
third-party line compiled is committed at a pinned commit and verified byte-identical to
upstream before a build is allowed to touch it.

There is one GPU — an RTX 5070 Ti, 15.92 GiB, sm_120 — and one lock. Every unit that wants
the card queues behind that lock, and that single constraint shapes most of what follows.

## State

Images work: 768×768 from the estate's own engine in **9.0 s**, measured inside a clean
root with the host's loader cache inhibited, with `libcuda.so.1` the only library permitted
to come from the host.

Text does not yet: `libllama` and `libggml` are packaged, but the chat unit has no weights
on this host, so nothing generates.

The gateway is designed and eight routes answer today — all eight in `/api/*`, a namespace
reserved for a dialect that is not ours.

## The three portals

Everything is in exactly one of them, and which one a file is in decides what may be done
to it.

```
SymonSayLearn/
│
├── upstream/ ══ PORTAL 1 ══ READ-ONLY. Third-party sources, each at its pinned commit.
│   │            Enters through ingest-tree; leaves as a disposable git archive export.
│   │            A diff that touches it any other way is a defect.
│   ├── api/ ················ http · model · web ········ the gateway's Python closure
│   ├── llm/ ················ inference ················· ggml · llama.cpp · triton · vllm
│   ├── diffuse/ ············ image ····················· stable-diffusion.cpp + 4 submodules
│   ├── ravencalc/ ·········· blas · numerics · symbolic · ml · dataframe · util · devtools
│   ├── common/ ············· ml · text · util · data ··· torch · transformers · tokenizers
│   ├── cli/ ················ mcp · anthropic · json · tls · http · auth · ffi · text · data
│   ├── crypto/ ············· stratum ··················· Stratum V2
│   ├── platform/ ··········· kernel · alienware ········ NVIDIA open kernel · AWCC
│   ├── build/ ·············· bitbake · autotools · ninja · devtools
│   └── adaptive-fabric/  live/  remix/  streamer/  web/
│
├── production/ ═ PORTAL 2 ═ WHAT SHIPS, AND WHAT PROVES IT.
│   ├── runtimes/ ··········· our code, one directory per runtime, mirroring upstream/
│   │                         api/ holds the API map: every route, C symbol and function
│   └── <area>/ ············· proof output: renders, clean-root traces, exit statuses
│
├── work/ ══════ PORTAL 3 ══ HOW IT GETS BUILT.
│   ├── recipes/ ············ the BitBake layer — three classes, one recipe group per runtime
│   ├── pins/ ··············· what is acquired, at which commit, verified how
│   ├── tools/ ·············· scan · verify · build · prove · generate
│   ├── output/ ············· bitbake tmp, downloads, sstate. gitignored, regenerable
│   └── config/  ops/  skills/  quarantine/
│
└── reports/ ═══ THE EXCEPTION ═ dated records. PHASE-INDEX.md is the one live board.
```

## What each one is

**`upstream/`** answers *what are you actually running?* It is not a vendor dump. Every
tree is committed at a commit, carries a `tree_sha`, and is re-verified against upstream at
every `do_unpack`. Nothing is ever compiled in place — a build compiles a throwaway export
— which is why the directory can be read-only and stay that way.

**`production/`** is the product and its proof in one place. `runtimes/` holds the code we
author, one directory per runtime, named for the unit it serves, so that a route, a unit, a
directory and a recipe group are the same word. Beside it sits the output that proves each
one: the render, the clean-root trace, the exit status. `production/runtimes/api/README.md`
is the API map — every route, C symbol and Python function, generated from the source.

**`work/`** is how anything gets built. `recipes/` carries three classes every recipe
inherits: `pristine` (the disposable export), `cuda` (one toolkit authority, one GPU
architecture, and a check that fails on any host library but the driver), `firstparty` (our
own trees exported from `HEAD`, so a package contains only what is committed). `pins/` is
the difference between *we build from source* and being able to show it — written by the
scanners, checked by the verifier, byte-identical across two runs or it is rejected.
`tools/` is grouped by verb. `output/` is bitbake's world and is never committed.

**`reports/`** is dated records. A report is true of the day it was written; it may name
any path in the project to say so, and it is never read back by anything.

## The linking rule

**Nothing in this project reaches across a portal by hard path. Every reference is resolved
inside the folder that owns it.**

Each portal — `upstream/`, `production/`, `work/` — is self-contained. A file in one refers
to a file in the same one by a path relative to that portal: never an absolute path, never a
walk through `..` into a sibling. Where one portal needs another, it goes through the
mapping that portal publishes for the purpose — the recipe's `SYMON_TREE`, the lock's
`source_path`, the endpoint register — and that mapping is the only crossing point. If the
map is wrong, one file is wrong; nothing else has to change.

`reports/` is the single exception. A report records where things were on the day it was
written and may name any path to do so. Nothing reads a report back, so a stale path in one
breaks nothing but the report.

What this buys: the project clones to any path, any portal relocates by changing one
mapping, and `grep -r '/home/' --exclude-dir=reports` is a complete audit.

Every directory holds exactly one `README.md`, and it maps that directory. There is no
`docs/` tree: documentation lives where the thing it describes lives.

Third-party sources under `upstream/` keep their own licences; the inventory is
`work/pins/license-inventory.json`.
