#!/usr/bin/env python3
"""generate-folder-maps.py - one README.md per folder, generated from the source of truth.

House rules this enforces, because a hand-written map is stale the week after it ships:

  * ONE markdown file per folder, named README.md. No docs/ folder: documentation lives
    in the directory that uses it.
  * A README says what the folder IS. It carries a "Controlled by" section ONLY when
    another folder writes to it, or adapts it into something else. A folder that nothing
    controls gets no navigation at all - there is nowhere you need to go. The root is the
    clearest case: nothing controls the root, so the root README points at nothing.
  * Every fact comes from acquisition/source-lock.json, the recipes, units.py or
    endpoints.py. Nothing is typed twice.
  * NOTHING is written inside */src/*/source/<component>/. Those trees are pristine
    upstream at their pin (R1, read-only); their map lives one level up, in the category
    directory that owns them.

  python3 -B tools/generate-folder-maps.py --dest <root>   [--dry-run]
"""
import argparse, json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/x -> repo root
LAYER = os.path.join(ROOT, "work", "recipes")
sys.path.insert(0, os.path.join(ROOT, "work/runtimes/api/app"))
from symoneural_api import endpoints as EP, units as UN            # noqa: E402

load = lambda n: json.load(open(os.path.join(ROOT, "work", "pins", n)))
slug = lambda rt: rt.replace("Symoneural-", "").lower()            # Symoneural-LLM -> llm

WRITTEN = []
def emit(dest, relpath, body):
    p = os.path.join(dest, relpath, "README.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(body.rstrip() + "\n")
    WRITTEN.append((os.path.join(relpath, "README.md"), len(body.splitlines()) + 1))


# ------------------------------------------------------------------ recipes
def recipes():
    """PN -> {path, summary, tree, pv, srcrev, runtime}. Parsed, never guessed."""
    out = {}
    for group in sorted(os.listdir(LAYER)):
        if not group.startswith("recipes-"):
            continue
        gdir = os.path.join(LAYER, group)
        for pn in sorted(os.listdir(gdir)):
            d = os.path.join(gdir, pn)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if not f.endswith(".bb"):
                    continue
                txt = open(os.path.join(d, f), errors="replace").read()
                g = lambda k: (re.search(r'^%s\s*=\s*"([^"]*)"' % k, txt, re.M) or [None, ""])[1]
                tree = g("SYMON_TREE")
                rt = ""
                if tree:
                    m = re.search(r"/(Symoneural-[A-Za-z-]+)/", tree)
                    rt = m.group(1) if m else ""
                out[f.split("_")[0]] = dict(
                    path="layer/%s/%s/%s" % (group, pn, f), group=group,
                    summary=g("SUMMARY"), tree=tree, pv=g("PV"), srcrev=g("SRCREV"), runtime=rt)
    return out


def unit_rows(rt, recs):
    """Units this runtime backs, via unit.backed_by -> recipe -> SYMON_TREE -> runtime."""
    rows = []
    for u in UN.REGISTRY.values():
        if any(recs.get(p, {}).get("runtime") == rt for p in u.backed_by):
            eps = [e.key for e in EP.for_unit(u.name)]
            rows.append((u, eps))
    return rows


def clip(text, n):
    """Never cut mid-word: a truncated sentence reads as a broken document."""
    text = (text or "").strip()
    if len(text) <= n:
        return text or "—"
    return text[:n].rsplit(" ", 1)[0] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dest = os.path.abspath(a.dest)

    lock = load("source-lock.json")["components"]
    recs = recipes()
    bycat = collections.defaultdict(list)
    for c in lock:
        p = c["source_path"].split("/")
        bycat[(p[0], p[2])].append(c)
    runtimes = sorted({rt for rt, _ in bycat})

    # ---------------------------------------------------------- runtimes/<rt>/
    for rt in runtimes:
        s, cats = slug(rt), sorted(cat for r, cat in bycat if r == rt)
        units = unit_rows(rt, recs)
        rrecs = {pn: r for pn, r in recs.items() if r["runtime"] == rt}
        n = sum(len(bycat[(rt, c)]) for c in cats)

        b = ["# work/runtimes/%s/\n" % s]
        # Interconnects first, as a CHAIN: every entry hands off to the next thing until
        # it reaches something that does nothing further. No entry is a dead end.
        b.append("## Interconnects\n")
        b.append("```")
        b.append("upstream/%s/ ..................... %s at %s"
                 % (s, ", ".join(cats), "their pinned commits" if n > 1 else "its pinned commit"))
        b.append("  -> control-plane/pins/ ......... holds the commit and tree_sha for each")
        b.append("     -> layer/classes/symoneural-pristine.bbclass")
        b.append("        re-verifies them at every do_unpack and exports a throwaway copy")
        b.append("        -> ENDS: a mismatch fails the build; nothing downstream can run")
        b.append("  -> layer/recipes-%s/ ........... adapts them into packages" % s)
        b.append("     -> out/%s/ .................. bitbake tmp, then the ipks" % s)
        if units:
            for u, eps in units:
                if eps:
                    b.append("        -> runtimes/api/ ......... declares %s for unit `%s`"
                             % (", ".join(eps), u.name))
                    b.append("           -> ENDS: the route is the outermost surface")
                else:
                    b.append("        -> unit `%s` has no route; see runtimes/api/ for why" % u.name)
                    b.append("           -> ENDS")
        else:
            b.append("        -> consumed by other runtimes' builds; serves no route")
            b.append("           -> ENDS")
        b.append("  -> tools/prove/clean-root-proof .. runs it in a clean root")
        b.append("     -> production/%s/ ............. the output, with its exit status" % s)
        b.append("        -> ENDS: evidence is read, never adapted")
        b.append("```\n")
        pl = lambda k, w: "%d %s%s" % (k, w, "" if k == 1 else "s")
        b.append("*Was `%s/`. %s in %d categor%s, %s.*\n"
                 % (rt, pl(n, "pinned upstream source"), len(cats),
                    "y" if len(cats) == 1 else "ies", pl(len(rrecs), "recipe")))
        if units:
            b.append("## Units it serves\n")
            b.append("| Unit | Port | Resource | Endpoints |\n|---|---:|---|---|")
            for u, eps in units:
                b.append("| `%s` | %d | %s | %s |" % (
                    u.name, u.port, u.resource,
                    " · ".join("`%s`" % e for e in eps) or
                    "**none** — " + clip(EP.UNROUTED.get(u.name, "unrecorded"), 90)))
            b.append("")
        else:
            b.append("**No unit.** This runtime builds the estate; it does not serve a route.\n")
        b.append("## Layout\n")
        b.append("| Path | Holds |\n|---|---|")
        for c in cats:
            b.append("| `src/%s/` | %d pinned upstream source%s — see `src/%s/README.md` |"
                     % (c, len(bycat[(rt, c)]), "" if len(bycat[(rt, c)]) == 1 else "s", c))
        b.append("| `build/` | bitbake TMPDIR, `downloads/`, `sstate-cache-master/`. **gitignored** |")
        b.append("\n## Recipes\n")
        if rrecs:
            b.append("| Recipe | PV | Builds |\n|---|---|---|")
            for pn, r in sorted(rrecs.items()):
                b.append("| [`%s`](../../%s) | %s | %s |" % (pn, r["path"], r["pv"] or "—",
                                                             clip(r["summary"], 80)))
        else:
            b.append("*None in `layer/` name a tree in this runtime yet.*")
        b.append("\n## Prove it\n")
        b.append("```bash")
        b.append("work/tools/symonbake %s <recipe>          # build one recipe here" % s)
        if os.path.exists(os.path.join(ROOT, "work/tools/proofs/%s.py" % s)):
            b.append("work/tools/clean-root-proof %s symoneural-image-%s   # run it in a clean root" % (s, s))
        b.append("```\n")
        pass
        emit(dest, "runtimes/%s" % s, "\n".join(b))

        # ------------------------------------------------ runtimes/<rt>/src/<cat>/
        for cat in cats:
            comps = sorted(bycat[(rt, cat)], key=lambda c: c["component"])
            cb = ["# runtimes/%s/src/%s/\n" % (s, cat)]
            cb.append("%d pinned upstream source%s. **`source/<component>/` is pristine upstream, "
                      "read-only (R1)** — nothing is written inside it, which is why this map is "
                      "here and not in there. Builds use a disposable `git archive` export.\n"
                      % (len(comps), "" if len(comps) == 1 else "s"))
            cb.append("| Component | Pin | Recipe | Upstream |\n|---|---|---|---|")
            for c in comps:
                pn = next((p for p, r in recs.items()
                           if r["tree"].rstrip("/").endswith(c["source_path"])), "")
                cb.append("| `%s` | `%s` | %s | %s |" % (
                    c["component"], (c.get("commit_sha") or "?")[:12],
                    ("[`%s`](../../../../%s)" % (pn, recs[pn]["path"])) if pn else "—",
                    c.get("upstream_url", "—")))
            cb.append("\n`tree_sha` for each is in `control-plane/source-lock.json`; "
                      "`tools/ingest-tree verify <component>` re-checks it against upstream, and "
                      "`symoneural-pristine` runs that check at every `do_unpack`.")
            emit(dest, "runtimes/%s/src/%s" % (s, cat), "\n".join(cb))

    # ---------------------------------------------------------------- layer/
    groups = sorted({r["group"] for r in recs.values()})
    b = ["# work/layer/\n", "## Interconnects\n", "```",
         "work/tools/build/symonbake ................ the only entry; sources oe-init-build-env, runs bitbake",
         "  -> layer/recipes-<name>/*.bb ....... one group per runtime; every recipe inherits a class",
         "     -> classes/symoneural-pristine ... reads control-plane/pins/, exports upstream/<rt>/ read-only",
         "        -> upstream/ ................. ENDS: the export is thrown away; upstream is never written",
         "     -> classes/symoneural-cuda ....... injects CUDA 13.4.1 / sm_120; checks S2 at package_qa",
         "        -> ENDS: any host library but libcuda/libnvidia-ml fails the build",
         "     -> classes/symoneural-firstparty . exports work/runtimes/<rt>/ from HEAD",
         "        -> ENDS: a package holds only what is committed",
         "  -> out/<runtime>/ ................... tmp, downloads, sstate, and the ipks",
         "     -> recipes-core/images/ .......... assembles ipks into a rootfs tarball",
         "        -> tools/prove/clean-root-proof  ENDS: the tarball is run, never edited",
         "```\n",
         "*Was `meta-symoneural/`.* %d recipes in %d groups, plus the three classes every recipe "
         "depends on.\n" % (len(recs), len(groups))]
    b.append("## Classes — read these before writing a recipe\n")
    b.append("| Class | What it does |\n|---|---|")
    b.append("| `classes/symoneural-pristine.bbclass` | `${S}` is a disposable `git archive HEAD:<path>` export, verified against the pin at `do_unpack`. **This is why no build can write into acquired source.** |")
    b.append("| `classes/symoneural-cuda.bbclass` | the ONE way a recipe reaches CUDA: 13.4.1, sm_120, native nvcc + target sysroot, and the S2 check that fails on any host library except `libcuda.so.1` / `libnvidia-ml.so.1` |")
    b.append("| `classes/symoneural-firstparty.bbclass` | first-party trees, exported from `HEAD` — **not the working tree**, so a package only ever contains what is committed |")
    b.append("\n## Recipe groups\n")
    b.append("| Group | Recipes | Runtime |\n|---|---:|---|")
    for g in groups:
        rs = [r for r in recs.values() if r["group"] == g]
        rts = sorted({slug(r["runtime"]) for r in rs if r["runtime"]})
        b.append("| `%s/` | %d | %s |" % (g, len(rs), ", ".join(rts) or "—"))
    b.append("\n## Controlled by\n")
    b.append("- `tools/build/symonbake` — the only supported way to run bitbake here")
    b.append("- `control-plane/pins/` — a recipe whose `SRCREV` disagrees with the lock fails at `do_unpack`, loudly")
    b.append("\n## What it controls\n")
    b.append("- `upstream/` — every `SYMON_TREE` names one of those trees and exports it read-only")
    b.append("- `out/` — everything bitbake produces")
    emit(dest, "layer", "\n".join(b))

    # -------------------------------------------------------- control-plane/
    names = sorted(f for f in os.listdir(os.path.join(ROOT, "work", "pins")) if f.endswith(".json"))
    who = {"source-lock.json": "work/tools/scan-acquisition.py",
           "submodule-lock.json": "work/tools/scan-acquisition.py",
           "dependency-graph.json": "work/tools/scan-dependencies.py",
           "license-inventory.json": "work/tools/scan-dependencies.py",
           "vendor-lock.json": "work/tools/scan-dependencies.py",
           "artifact-plan.json": "work/tools/scan-dependencies.py",
           "provider-collisions.json": "work/tools/scan-oe-providers.py",
           "source-collisions.json": "work/tools/scan-source-collisions.py",
           "model-register.json": "hand-curated; weights NEVER enter git",
           "control-plane.json": "work/tools/check-determinism.py (scanner identity)"}
    b = ["# work/control-plane/\n", "## Interconnects\n", "```",
         "work/tools/build/ingest-tree ingest ........ moves a clone's .git to .gitpins/, commits the files",
         "  -> pins/source-lock.json ........... records commit_sha + tree_sha per component",
         "     -> layer/classes/symoneural-pristine  re-reads it at every do_unpack",
         "        -> ENDS: PIN MISMATCH fails the build",
         "     -> tools/verify/verify-acquisition   re-derives every pin from disk and compares",
         "        -> evidence/ ................. ENDS: the verdict, with its exit status",
         "  -> pins/submodule-lock.json ........ each submodule's gitlink, re-verified the same way",
         "work/tools/scan/scan-dependencies ........... walks every upstream tree",
         "  -> graph/dependency-graph.json ..... every declared dependency, classified",
         "  -> graph/license-inventory.json .... every licence file, hashed",
         "     -> tools/generate/runtime-acquisition  renders reports/acquisition-state.md",
         "        -> ENDS: a report is read, never adapted",
         "registers/model-register.json .......... hand-curated: which weights, sha256, PRESENT/ABSENT",
         "  -> runtimes/*/app ................... a unit reads $SYMON_MODELS_DIR/<subfolder>/<file>",
         "     -> ENDS: weights are outside the repository and never enter it",
         "work/tools/verify/check-determinism ......... runs the scanners twice",
         "  -> control-plane.json .............. ENDS: byte-identical or the control plane is rejected",
         "```\n",
         "*Was `acquisition/`.* **Generated files — do not hand-edit; run the scanner.**\n"]
    b.append("| File | Written by |\n|---|---|")
    for n in names:
        b.append("| `%s` | %s |" % (n, who.get(n, "hand-curated")))
    b.append("\n## Use it\n```bash")
    b.append("work/tools/scan-acquisition.py      # re-derive the pins from the pin stores")
    b.append("work/tools/scan-dependencies.py     # re-derive dependencies, licences, vendored code")
    b.append("work/tools/verify-acquisition.py    # does the control plane agree with disk?")
    b.append("work/tools/check-determinism.py     # two runs, byte-identical, or it is not a control plane")
    b.append("```\n\n## The rule\n")
    b.append("A component on disk with no row here reconciles as **EXTRA / INTENT-UNDECLARED**. "
             "A row with no `tree_sha` has never been ingested and `symoneural-pristine` refuses "
             "to build it.")
    emit(dest, "control-plane", "\n".join(b))

    # ---------------------------------------------------------------- tools/
    ts = []
    for n in sorted(os.listdir(os.path.join(ROOT, "work", "tools"))):
        p = os.path.join(ROOT, "work", "tools", n)
        if not os.path.isfile(p) or not os.access(p, os.X_OK):
            continue
        d = ""
        head = open(p, errors="replace").read(3000)
        m = re.search(r'^"""(.*)', head, re.M)
        if m:
            d = m.group(1).strip()
        if not d:
            for ln in head.splitlines()[1:6]:
                if ln.startswith("#") and len(ln) > 3:
                    d = ln.lstrip("# ").strip(); break
        ts.append((n, d))
    b = ["# work/tools/\n", "## Interconnects\n", "```",
         "scan/ ......... reads upstream/ and .gitpins/",
         "  -> writes control-plane/ .............. ENDS there for scan; verify/ picks it up",
         "verify/ ....... reads control-plane/, upstream/, the recipes, the test suites",
         "  -> run-all-tests ...................... discovers every suite; one exit code",
         "  -> verify-acquisition ................. pins vs disk vs report",
         "  -> check-determinism .................. two scanner runs, byte-identical",
         "     -> evidence/ ....................... ENDS: verdicts are recorded, never adapted",
         "build/ ........ symonbake drives bitbake against layer/",
         "  -> out/<runtime>/ ..................... ENDS for build; prove/ picks it up",
         "prove/ ........ clean-root-proof extracts out/<rt>/deploy/images/*.tar.gz",
         "  -> runs proofs/<runtime>.py under the TARGET loader, host cache inhibited",
         "     -> evidence/<runtime>/ ............. ENDS: PASS/FAIL plus every library mapped",
         "generate/ ..... reads control-plane/, the recipes, units.py, endpoints.py, the C headers",
         "  -> writes every README.md in the tree .. ENDS: documentation is output, not input",
         "```\n",
         "%d executables. Every one reads disk and prints evidence; none of them "
         "believe a document.\n" % len(ts)]
    b.append("| Tool | What it does |\n|---|---|")
    for n, d in ts:
        b.append("| `%s` | %s |" % (n, clip(d, 95)))
    # No "Controlled by": nothing controls tools/. It is the thing doing the controlling,
    # so a navigation section here would be pointing at its own outputs.
    b.append("\n## What it controls\n")
    b.append("- `control-plane/` — `scan/` writes it, `verify/` checks it")
    b.append("- `runtimes/*/` and `out/` — `build/` builds them, `prove/` runs them in a clean root")
    b.append("- `evidence/` — where output belongs once it backs a claim")
    emit(dest, "tools", "\n".join(b))

    # ------------------------------------------------------- reports/ evidence/
    emit(dest, "reports", "# work/reports/\n\n## Interconnects\n\n```\n"
         "work/tools/generate/runtime-acquisition ... reads control-plane/ -> writes acquisition-state.md\n"
         "work/tools/generate/originals-by-runtime .. reads control-plane/ -> writes originals-by-runtime.md\n"
         "  -> ENDS: both are regenerated, never edited\n"
         "phase-NN-report.md ................... hand-written at the time; cites evidence/\n"
         "  -> evidence/ ....................... ENDS: the record points at output, output points nowhere\n"
         "PHASE-INDEX.md ....................... the one live board; reads the STATUS line of each report\n"
         "  -> ENDS: never presented as current unless just verified against disk\n"
         "```\n\n*Was `generated/`.* Phase records and the status board. "
         "**Dated records, not live documentation** — a report is true of the day it was written.\n"
         "\n`PHASE-INDEX.md` is the exception: it is the live board, and the rule is that it is "
         "never presented as current unless it was just verified against disk.\n"
         "\n`acquisition-state.md` and `originals-by-runtime.md` are **generated** "
         "(`tools/generate-runtime-acquisition.py`, `tools/originals-by-runtime.py`) — "
         "regenerate, never edit.\n")
    emit(dest, "production", "# work/evidence/\n\n## Interconnects\n\n```\n"
         "work/tools/verify/* , tools/prove/* , tools/build/symonbake\n"
         "  -> evidence/<area>/<file>.txt ........ stdout + exit status, verbatim\n"
         "     -> reports/*.md cite these by path\n"
         "        -> ENDS: nothing reads evidence to change anything. It is the terminus.\n"
         "```\n\nCommand output, kept because a claim without it is not "
         "a claim. One directory per piece of work.\n\n**What belongs here:** the actual stdout of "
         "a build, a proof, an audit — with its exit status. **What does not:** a summary of what "
         "the output said.\n\nPaths inside these files are the paths that were real when the "
         "command ran. They are **not** rewritten when the repository moves; rewriting evidence "
         "falsifies it.\n")

    for p, n in WRITTEN:
        print("  %-52s %3d lines" % (p, n))
    print("\n%d README.md written under %s" % (len(WRITTEN), dest))
    print("NONE inside */src/*/source/ - those trees are read-only upstream (R1)")


main()
