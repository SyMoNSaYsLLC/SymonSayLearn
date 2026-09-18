# symoneural-learn — repository assessment, 2026-09-18

Asked by Garrett: "assess the symoneural-learn repo and rethink the config folder."
Everything below was read from disk or a command; where I acted, the commit is named.

Repository: https://github.com/SyMoNSaYsLLC/symoneural-learn (private). Assessed at `223d932`;
changes landed as `6a1135a`.

---

## 1. What the repository actually is

A **curated mirror** of first-party pieces of the estate, not yet a product that installs from
what is pushed:

| Directory | Relation to the estate | Standalone? |
|---|---|---|
| `gateway/symoneural_gateway/` | the four dialect modules of `work/runtimes/api/app/symoneural_api/`, byte-identical modulo the package name | imports fine (fastapi, httpx, siblings only) — but had **no `pyproject.toml`, no `__init__.py`**, so nothing could install it. **Fixed** in `6a1135a`: `pip install ./gateway` builds `symoneural_gateway-1.0.0-py3-none-any.whl`, console script `symoneural-gateway`, verified in a fresh venv. |
| `web/` | identical to `work/runtimes/web/app` (source, lockfile, no node_modules) | yes — `corepack pnpm install --frozen-lockfile` + `next build`; pnpm itself is not usable offline on this host |
| `runtime/` | identical to `work/runtimes/llm/hostrun` | yes — shell; defaults were `/home/google/...`, now `$HOME/...` |
| `recipes/` | six recipes copied from the estate layer | **no** — they `inherit symoneural-firstparty` (an estate class), point `SYMON_FP_PATH` at `work/runtimes/...` (estate layout), and there is no `conf/layer.conf`. They document how the estate packages the product; they cannot build here. README now says so. |
| `config/` | see §3 | — |
| `tools/` | licence audit, ship gate, release cutter | yes |
| `docs/` | empty, untracked directory | — |

**Consequence for "100 % installable and reproducible from what is pushed":** true today for
`gateway/` (wheel), `runtime/` (scripts) and `web/` (source build with network); **not true**
for the BitBake path, and there is no BitBake build directory on `/home` at all — `symonbake`
sources `oe-init-build-env` from `/home/google/symoneural-bootstrap-master`, which exists only on
the Satechi. The last real image deploys sit on the source disk under dead-mount configs.

## 2. Findings that are not about layout

1. **The estate's own licence audit fails every previously built image**, and not only on gdbm:
   `util-linux-flock` and `update-alternatives-opkg` ship as **GPL-2**, and
   `symoneural-image-learn.bb`'s `INCOMPATIBLE_LICENSE` **omits `GPL-2.0*`**. My earlier statement
   that util-linux's shipped binaries were "the permissive parts" was wrong. A non-copyleft OE
   image means replacing busybox, opkg's alternatives and parts of util-linux — a distro-policy
   change list is being produced by the `noncopyleft-image-policy` agent of workflow
   `wf_a27cb9e1-4ba`; the recipe is left as-is until that list exists, so the gap is recorded
   here rather than papered over.
2. **The recipe advertised systemd user units that exist in neither repository.** Fixed the
   `SUMMARY`/`DESCRIPTION`/comment in both copies (`6a1135a`, estate `267721a65`).
3. **`web/pnpm-lock.yaml` carried a licence header** put there by my own SPDX script — a generated
   file must never be stamped. Removed; `web/package.json` gained the missing `license` field.
   Both files are again byte-identical to the estate.
4. **Prebuilt x86-64 ELF test binaries are git-tracked in the estate**
   (`work/runtimes/api/app/tests/native/test_*`). Build output in git; not in the product repo.
   Named, not acted on.
5. **Operator identifiers remain in the product repo's git history** (the removed dumps: 11
   Anthropic account/org UUIDs, home paths, one personal e-mail — `tools/ship-gate.py --repo .`
   now lists them as REVIEW). The working tree is clean of them. The repo becomes Apache-2.0 two
   years after each release, so history is eventually public. Removing them needs a history
   rewrite and a force-push of a repo that is one hour old — cheap now, expensive later. **Your
   decision**; not done.

## 3. The config folder — what was there, and what it is now

### Before

`config/claude-desktop/` — ten files, all about one third-party client:

- 5 were **Claude Desktop's own application state exported from the live profile**:
  `claude_desktop_config.json` (account UUIDs, org UUID, `bypassPermissionsGateByAccount`,
  `localAgentModeTrustedFolders` listing your Desktop and Downloads, and an `mcpServers` path
  pointing at the **dead mount** `/home/google/SymonSaysLLC/tools/mcp/...`),
  `extensions-blocklist.json` (org blocklist URL), `mcp-user-tool-toggles.json` (account
  UUIDs), `os-entry-points.json` (account + org UUIDs), `symonAI.live-export.json` (a snapshot
  of what the profile held before the directory existed). **Nothing installed them** — the
  installer applies only `symonAI.json` — and none of it configures the product.
- 5 were legitimate: the tracked declaration (no credential), its installer, two measured
  settings documents, an index.
- Meanwhile the product's **own** configuration — about 25 `SYM_*` variables read by the
  gateway, the web UI and the chat-unit scripts — was declared nowhere. Defaults were scattered
  across shell, Python and prose, several of them `/home/google/...` absolute paths.

### The rule the folder now follows

`config/` holds **declarations the product reads**. Not application state exported from some
program's profile, nothing host-specific by accident, never a secret or a weight. Assume it will
be public (Apache-2.0 after two years) and write it that way.

### After (`6a1135a`)

```
config/
  README.md                        the rule, the layout, what is deliberately not here
  symoneural-learn.env.example     THE CONTRACT: every SYM_* variable, its default, its reason
  clients/
    claude-desktop/                the reference third-party client
      README.md                    (was claude-desktop.md; estate paths repointed at this repo)
      symonAI.json                 declaration, no credential; host paths → SYM_* names
      apply-symonAI-config.sh      installer; refuses while the app runs
      claude-desktop-settings.md   every setting with its measured reason; host paths generalised
      ssh-code-surface.md          SSH surface values; personal e-mail and home paths scrubbed
```

Removed from the product: the five application-state exports. Identical bytes remain tracked in
the estate at `work/config/claude-desktop/` as dated evidence — moved in effect, not deleted.

### What is deliberately not in `config/`

- the gateway credential (only in the file named by `SYM_GW_KEY_FILE`, 0600);
- weights (`SYM_MODELS_DIR` points outside the tree);
- client application state (above);
- **model cards** — `symon-chat`/`symon-coder`/`symon-work` are code in `models.py`. Moving them
  to data under `config/models/` is the natural next step once the engine behind `/v1` is the
  estate's own (mistral.rs per `reports/rust-engine-eval-2026-09-18.md`). Recorded, not built.

## 4. Verification of what changed

| Claim | Evidence |
|---|---|
| gateway installs from the repo | `pip install ./gateway` rc=0 in a fresh venv; `import symoneural_gateway` → `__version__ 1.0.0`; wheel `symoneural_gateway-1.0.0-py3-none-any.whl` built |
| no host paths or personal e-mail left in `config/` | `grep -rn -E '/home/google\|@gmail' config/` → 0 lines |
| `symonAI.json` still valid JSON after edits | `json.loads` rc=0 on both copies |
| runtime scripts still parse, identical in both repos | `bash -n` rc=0; `diff -q` product vs estate → identical |
| web files identical to the estate again | `diff -q` on `package.json` and `pnpm-lock.yaml` → identical |
| ship gate on the product repo | `tools/ship-gate.py --repo .` → no FAIL; REVIEW = identifiers in history (§2.5) |
| pushed | remote `main` = local `main` = `6a1135a` |

## 5. Named and not done

- History rewrite to remove the identifiers (§2.5) — your call.
- Making `recipes/` a real layer in the product repo (its own `conf/layer.conf`, the
  `symoneural-firstparty` class, `SYMON_FP_PATH` relative to this repo) — or stating plainly that
  BitBake packaging lives in the estate and the product repo ships wheels/tarballs/binaries.
  The second is what the release notes will say for v1.0.0.
- `docs/` is empty: either give it the cross-cutting documents (release process, the engine
  substitution record) or remove the directory from the README.
- Model cards to data (`config/models/`).
- The estate's tracked prebuilt test binaries (§2.4).
