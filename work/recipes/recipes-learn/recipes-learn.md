# recipes-learn

The recipes for `symoneural-learn`: the composed runtime for this build.

## What makes this directory different

Every other `recipes-*` directory in this layer builds a COMPONENT: a library, a
Python distribution, an engine. This one builds the COMPOSITION — the thing a person
installs to get the product, and the thing that carries a version number and a
release. `symoneural-learn` 1.0.0 is what "the SymonSayLearn runtime, v1.0.0" means.

## Files

| Recipe | Produces | State |
|---|---|---|
| `symoneural-learn/symoneural-learn_1.0.0.bb` | bring-up scripts and `SOURCE-TREE` | builds |
| `symoneural-learn-web/symoneural-learn-web_1.0.0.bb` | the web interface | **blocked**, see below |

And in `recipes-core/`, because that is where this layer keeps them:

| Recipe | Role |
|---|---|
| `packagegroups/packagegroup-symoneural-learn.bb` | the composition |
| `images/symoneural-image-learn.bb` | clean-root proof image; what a release is cut from |

## Interfaces

| Direction | What |
|---|---|
| Composes | `packagegroup-symoneural-api`, `packagegroup-symoneural-llm`, `packagegroup-symoneural-common` |
| Recommends | `symoneural-learn-web`, `packagegroup-symoneural-cli` |
| Installs to | `${libexecdir}/symoneural-learn/`, `${datadir}/symoneural-learn/SOURCE-TREE` |
| Reads at run time | `SYM_MODELS_DIR`, `SYM_CHAT_URL`, `SYM_GW_KEY_FILE` |
| Never installs | weights, credentials |

The packagegroup names other **packagegroups**, not their members. A group that
re-lists what another already declares drifts the moment that group changes, and then
two files disagree about one closure. Adding a package to the LLM runtime reaches
this runtime without anyone editing a file here.

## Two barriers, recorded rather than worked around

**The web interface cannot build.** Next.js, React and Node.js are not acquired into
this estate. `upstream/web/` holds `workerd` and `workers-sdk` only, and no recipe
provides a target Node interpreter. The host build that exists today at
`work/runtimes/web/app/node_modules` came from the public npm registry, which is how
Next.js is consumed but is **not** acquisition: that tree is not pinned in
`acquisition/`, not committed, and not verifiable against an upstream commit. Three
acquisitions unblock it, listed in the recipe header. Until then
`symoneural-image-learn` excludes the package by design so the image still builds.

**The chat unit's engine is a substitution.** It is an acquired upstream build run
from a host virtualenv, not `symoneural-llm`. Rules section 3.10 governs that, and it
means `symoneural-learn` cannot package the engine. When an estate build replaces it,
the engine becomes an `RDEPENDS` row here and the `SYM_CHAT_ENGINE_VENV` default in
`serve-chat-unit.sh` disappears.

## A parse-time mistake worth keeping

The first version of `symoneural-learn-web` refused via `bb.fatal` inside an
anonymous `python () { }` block. BitBake parses **every** recipe in the layer on
**every** build, so that would have failed every build in the estate rather than only
an attempt to build this package. A recipe that cannot be satisfied must still parse
cleanly and fail only when someone asks for it, which is why the refusal is in
`do_compile`.

## Onward

The runtime this composes is documented in
`work/runtimes/api/app/symoneural_api/symoneural_api.md` (the gateway and its
endpoint register) and `work/runtimes/llm/hostrun/hostrun.md` (the chat unit and its
bring-up ladder). Read the gateway document first; it holds the endpoint register and
the credential model that everything else assumes.
