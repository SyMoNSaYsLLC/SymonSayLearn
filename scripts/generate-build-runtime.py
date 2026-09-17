#!/usr/bin/env python3
"""generate-build-runtime.py — writes the symoneural-build runtime's toolset.

scripts -> source -> project code. This is the scripts tier: it READS the OE/bitbake
toolset pinned in upstream/build and the estate's own tools in work/tools, and WRITES
production/runtimes/build/bin/symon* — one wrapper per verb — plus that runtime's README
from the same table. Nothing in production/runtimes/build is hand-typed.

Every wrapper:
  * requires SYMON_REPO (symonlearn sets it); never guesses its own location
  * resolves its target INSIDE the portal that owns it — upstream/ for OE tools,
    work/tools for ours — through this table and nowhere else (the linking rule)
  * exports OEROOT/BITBAKEDIR for the OE tools so they find the PINNED trees

  python3 scripts/generate-build-runtime.py            # writes bin/ and README.md
  python3 scripts/generate-build-runtime.py --check    # exit 1 if bin/ is stale
"""
import argparse, os, stat, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "production", "runtimes", "build")
OE   = "upstream/build/devtools/openembedded-core"
BB   = "upstream/build/bitbake/bitbake"

# verb -> (portal-relative target, one line). Grouped the way the first build ran:
# ACQUIRE -> BUILD -> PROVE -> RECORD -> GENERATE, with OE's own tools under their lineage.
VERBS = {
  # ---- ACQUIRE: pin an upstream tree, verify it forever
  "symonpin":       ("work/tools/ingest-tree",                 "clone at a commit, move .git to .gitpins, commit the files at their pin"),
  "symonverify":    ("work/tools/ingest-tree verify",          "HEAD:<path> tree_sha == the lock, every submodule gitlink too"),
  "symonscan":      ("work/tools/scan-acquisition.py",         "re-derive pins and submodules from the pin stores into work/pins"),
  "symondeps":      ("work/tools/scan-dependencies.py",        "re-derive dependencies, licences, vendored code into work/pins"),
  "symonlock":      ("work/tools/verify-acquisition.py",       "does disk agree with the lock, and the lock with the report"),
  # ---- BUILD: turn a pinned tree into packages
  "symonbake":      (None,                                     "bitbake, one runtime's build dir, background priority"),   # hand-kept: it IS the launcher
  "symonbuild":     ("work/tools/build-all",                   "every runtime, in parallel, per-run logs"),
  "symonguard":     ("work/tools/edit-guard",                  "is a cooker live? never edit a recipe while one is"),
  "symonnice":      ("work/tools/nice-builds",                 "renice every live bitbake to background priority"),
  "symonlayers":    (BB + "/bin/bitbake-layers",               "show, add, remove layers in a build dir            (bitbake-layers)"),
  "symongetvar":    (BB + "/bin/bitbake-getvar",               "one variable's value as bitbake sees it            (bitbake-getvar)"),
  "symondiffsigs":  (BB + "/bin/bitbake-diffsigs",             "why did a task re-run? diff its signature           (bitbake-diffsigs)"),
  "symondev":       (OE + "/scripts/devtool",                  "modify, add, upgrade a recipe in a workspace       (devtool)"),
  "symonrecipe":    (OE + "/scripts/recipetool",               "create a recipe from a source tree                  (recipetool)"),
  "symonpkgdata":   (OE + "/scripts/oe-pkgdata-util",          "what package owns a file; what a package ships     (oe-pkgdata-util)"),
  "symondepends":   (OE + "/scripts/oe-depends-dot",           "the dependency graph as dot                        (oe-depends-dot)"),
  "symonsstate":    (OE + "/scripts/oe-check-sstate",          "which tasks would come from sstate                 (oe-check-sstate)"),
  "symonnative":    (OE + "/scripts/oe-run-native",            "run a native-sysroot binary                        (oe-run-native)"),
  # ---- PROVE: did it work, on disk, with nothing leaking in
  "symonprove":     ("work/tools/clean-root-proof",            "extract the image, run under the target loader, host cache inhibited, report every library mapped"),
  "symontest":      ("work/tools/run-all-tests",               "every test suite in the estate, discovered not listed"),
  "symonlinkage":   ("work/tools/check-native-linkage.py",     "native linkage audit: who defines what, no RUNPATH into a build"),
  "symonclosure":   ("work/tools/check-python-runtime-closures.py", "the Python dependency gate, from wheel METADATA"),
  "symonemulate":   (OE + "/scripts/runqemu",                  "boot an image under qemu                           (runqemu)"),
  "symonselftest":  (OE + "/scripts/oe-selftest",              "OE's own selftest against this layer              (oe-selftest)"),
  # ---- RECORD: make the claim checkable later
  "symonhash":      ("work/tools/check-evidence-hashes.py",    "every production/ SHA256SUMS still matches its files"),
  "symondeterm":    ("work/tools/check-determinism.py",        "two scanner runs, byte-identical, or it is not a control plane"),
  "symonhistory":   ("work/tools/check-history.sh",            "has this failed before?"),
  "symonfacts":     ("work/tools/estate-facts",                "host truth: driver, GPU, listeners, disk"),
  # ---- GENERATE: scripts/ writes source; never hand-typed
  "symonmap":       ("scripts/generate-api-map.py",            "the API map: every route, C symbol, function, from the source"),
  "symondocs":      ("scripts/generate-folder-maps.py",        "one README per folder, interconnects first, no dead ends"),
  "symonreport":    ("scripts/generate-runtime-acquisition.py","acquisition-state.md and the phase board from work/pins"),
  "symontoolset":   ("scripts/generate-build-runtime.py",      "this: regenerate production/runtimes/build/bin from the table"),
}

WRAPPER = '''#!/usr/bin/env bash
# {verb} — {line}
# GENERATED by scripts/generate-build-runtime.py; ships with symoneural-build. Do not edit.
: "${{SYMON_REPO:?symonlearn not sourced: SYMON_REPO is unset}}"
export OEROOT="$SYMON_REPO/{oe}" BITBAKEDIR="$SYMON_REPO/{bb}"
export PATH="$BITBAKEDIR/bin:$OEROOT/scripts:$PATH"
exec {target} "$@"
'''

def target_for(rel):
    parts = rel.split(" ", 1)
    path, extra = parts[0], (" " + parts[1] if len(parts) > 1 else "")
    runner = "python3 -B " if path.endswith(".py") else ""
    return '%s"$SYMON_REPO/%s"%s' % (runner, path, extra)

def render():
    files = {}
    for verb, (rel, line) in sorted(VERBS.items()):
        if rel is None:
            continue                                        # symonbake is the hand-kept launcher
        files[verb] = WRAPPER.format(verb=verb, line=line, oe=OE, bb=BB, target=target_for(rel))
    return files

def readme():
    o = ["# production/runtimes/build/", "",
         "**The build runtime — what every other runtime is built with.** `symonlearn` activates it;",
         "these are its verbs. Every wrapper here is GENERATED by `scripts/generate-build-runtime.py`",
         "from one table; it resolves its target inside the portal that owns it and reads",
         "`SYMON_REPO` rather than guessing where it is.", "",
         "## Interconnects", "", "```",
         "symonlearn (root) ........... exports SYMON_REPO, SYMON_OUT; puts bin/ on PATH",
         "  -> bin/symon* .............. one verb each; OE verbs export OEROOT/BITBAKEDIR",
         "     -> upstream/build/ ....... the PINNED bitbake + openembedded-core the OE verbs run",
         "        -> ENDS: upstream is read, never written",
         "     -> work/tools/ ........... the estate's own tools, by the same wrappers",
         "        -> work/pins/ .......... symonscan/symondeps write it; symonlock checks it -> ENDS",
         "     -> work/output/<rt>/ ..... symonbake builds into it; symonprove reads the image from it",
         "        -> production/<area>/ .. the proof output -> ENDS: evidence is read, never adapted",
         "```", "",
         "## Verbs", "", "| Verb | Does | Lineage |", "|---|---|---|"]
    for verb, (rel, line) in sorted(VERBS.items()):
        lineage = "OE / bitbake" if rel and rel.startswith("upstream/") else ("scripts/" if rel and rel.startswith("scripts/") else "estate")
        o.append("| `%s` | %s | %s |" % (verb, line.split("  (")[0].strip(), lineage))
    o += ["", "`symonbake` is the one hand-kept file here: it is the launcher itself, the thing the",
          "wrappers hand off to. `estate_processes.py` is its cooker-visibility check.", ""]
    return "\n".join(o)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); a = ap.parse_args()
    bindir = os.path.join(OUT, "bin"); os.makedirs(bindir, exist_ok=True)
    files = render(); stale = []
    for verb, body in files.items():
        p = os.path.join(bindir, verb)
        cur = open(p).read() if os.path.exists(p) else None
        if cur != body:
            stale.append(verb)
            if not a.check:
                open(p, "w").write(body); os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    rp = os.path.join(OUT, "README.md"); rd = readme()
    if (open(rp).read() if os.path.exists(rp) else None) != rd:
        stale.append("README.md")
        if not a.check: open(rp, "w").write(rd)
    if a.check:
        print("stale: %s" % (", ".join(stale) or "none")); sys.exit(1 if stale else 0)
    print("wrote %d verbs + README.md into %s (%d changed)" % (len(files), os.path.relpath(OUT, ROOT), len(stale)))

main()
