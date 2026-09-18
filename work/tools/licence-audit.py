#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""licence-audit - prove what licences reach the product, from disk, every run.

The claim this exists to support is narrow and testable:

    No strong or network copyleft licence reaches the SymonSayLearn runtime.

A claim like that is worthless as prose. It has to be recomputed from the
repository whenever anything changes, and it has to FAIL LOUDLY when it stops
being true. So this is a generator with a --check mode, not a document.

WHAT IT READS, in order of authority
------------------------------------
1. production/*/[A-Z]*-INSTALL-MANIFEST.txt
   Ground truth. These are the package lists of root filesystems that were
   actually assembled by opkg from the package feed. A package in one of these
   files SHIPPED. Nothing else is as strong: a recipe's RDEPENDS is intent, a
   manifest is what happened.

2. work/recipes/**/*.bb
   The licence declared for each recipe, plus its pin.

3. work/pins/source-lock.json
   The per-component recipe_LICENSE recorded at acquisition, used to
   cross-check (2). Where the two disagree the audit says so rather than
   picking one.

KNOWN LIMITATION, stated because it changes how to read the output
------------------------------------------------------------------
A recipe's top-level LICENSE is the union across its whole source tree, not the
licence of each binary package it produces. OpenEmbedded expresses the precise
answer with per-package overrides (LICENSE:${PN}-foo), and reading those
correctly needs bitbake's parser, not this one.

So a recipe-level result here is an UPPER BOUND. util-linux, xz and bzip2 each
declare GPL in their union while the packages that actually ship from them
(libuuid1, liblzma5, libbz2-1) are the permissive parts. Treat a STRONG_COPYLEFT
row as "investigate this", not as "this is GPL". The row that needs no
investigation is one where the recipe declares a single copyleft token, as gdbm
does with GPL-3.0-only.

WHAT IT REFUSES TO DO
---------------------
Report a package as clean because it could not be resolved. An unresolved
package is reported as UNRESOLVED and counts against the audit, because the
failure mode this guards against is exactly "we did not find a problem" being
mistaken for "there is no problem".

Usage:
    licence-audit.py                 write the report to production/licence/
    licence-audit.py --check         exit 1 if copyleft ships or rows are unresolved
    licence-audit.py --print         write nothing, print the summary
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Every layer whose recipes can produce a package that lands in an image.
#
# The SyMoNeuRaL layer alone is NOT enough, and assuming it was is exactly the
# error this tool exists to catch. A first run resolved only 21 of 99 packages in
# the API image; the other 78 — glibc, libgcc, the Python stdlib split, zlib,
# openssl — come from the acquired OpenEmbedded core, and those are precisely the
# packages most likely to carry LGPL or GPL-with-exception terms. Reporting them
# as "not found" and moving on would have produced a clean-looking audit that
# proved nothing.
RECIPE_ROOTS = [
    ROOT / "work" / "recipes",
    ROOT / "upstream" / "build" / "devtools" / "openembedded-core",
    ROOT / "upstream" / "build" / "bitbake",
]

# ---------------------------------------------------------------------------
# Licence classification.
#
# The categories are chosen by what an obligation DOES when you distribute a
# binary, not by how the licence is usually described. That is the only
# distinction that matters to the question being asked.
# ---------------------------------------------------------------------------
PERMISSIVE = {
    "MIT", "MIT-0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Apache-2.0",
    "PSF-2.0", "CC0-1.0", "Unlicense", "Zlib", "CNRI-Python", "BSD-4-Clause",
    "Python-2.0", "0BSD", "BSL-1.0", "PD", "bzip2-1.0.6", "Libpng", "OpenSSL",
    "BSD-4-Clause-UC", "HPND", "X11", "FTL", "NCSA", "Artistic-1.0", "Sleepycat",
    "MIT-open-group", "bzip2-1.0.4", "Unicode-DFS-2016", "curl", "ICU",
}

# GPL WITH an exception that explicitly permits linking into non-GPL works.
# libgcc is the one that matters here: without its Runtime Library Exception,
# every binary a GCC toolchain produces would be GPL. Treating it as strong
# copyleft would be wrong; treating it as permissive would hide the exception.
GPL_WITH_LINKING_EXCEPTION = {
    "GPL-3.0-with-GCC-exception", "GPL-3.0-or-later-with-GCC-exception",
    "GPL-2.0-with-GCC-exception", "GCC-exception-3.1",
}

# File-level copyleft. Obligation attaches to the licensed FILES only: publish
# modifications to those files. Linking proprietary code to them is permitted,
# so these do not force the product open — but they are reported, because
# "we modified none of them" is a claim someone has to be able to check.
WEAK_FILE_COPYLEFT = {"MPL-2.0", "MPL-1.1", "EPL-2.0", "CDDL-1.0"}

# Library copyleft. Dynamic linking permitted provided the user can relink.
# Reported separately because the obligation is real but does not open the
# product.
WEAK_LIB_COPYLEFT = {"LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
                     "LGPL-3.0-or-later", "LGPL-2.0-only", "LGPL-2.0-or-later"}

# Strong copyleft. Linking these into a distributed work licenses the whole
# work under them. THIS is the category that would end a proprietary product.
STRONG_COPYLEFT = {"GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only",
                   "GPL-3.0-or-later", "GPL-1.0-or-later"}

# Network copyleft. Strong, and triggered by serving over a network rather than
# by distributing a binary — which is precisely what this product does, so it
# would be the most dangerous category to get wrong.
NETWORK_COPYLEFT = {"AGPL-3.0-only", "AGPL-3.0-or-later", "SSPL-1.0"}

PROPRIETARY = {"CLOSED"}

CATEGORY_ORDER = [
    ("NETWORK_COPYLEFT", "network copyleft — would reach a served product"),
    ("STRONG_COPYLEFT", "strong copyleft — would open a distributed product"),
    ("GPL_LINKING_EXCEPTION", "GPL with a linking exception — permits non-GPL linking"),
    ("WEAK_LIB_COPYLEFT", "library copyleft — relink obligation"),
    ("WEAK_FILE_COPYLEFT", "file copyleft — publish modifications to those files"),
    ("PROPRIETARY", "SyMoNeuRaL's own code"),
    ("PERMISSIVE", "permissive — attribution only"),
    ("LICENSEREF", "vendor terms, reviewed individually"),
    ("UNRESOLVED", "NOT RESOLVED — counts against the audit"),
]

# Categories whose presence in a SHIPPED closure fails --check.
FAILING = {"STRONG_COPYLEFT", "NETWORK_COPYLEFT", "UNRESOLVED"}


def classify(expr: str) -> tuple[str, str]:
    """Classify an SPDX expression. Returns (category, reasoning).

    Dual licences matter and are handled explicitly. `MIT OR GPL-2.0-only` is
    NOT a GPL component: the recipient chooses, and this estate chooses MIT.
    Collapsing an OR to its most restrictive half would manufacture a problem
    that does not exist, which is its own kind of dishonesty.
    """
    if not expr:
        return "UNRESOLVED", "no LICENSE declared"

    e = expr.strip()

    # A top-level OR: satisfied by any one operand. Take the least restrictive.
    if " OR " in e and " AND " not in e:
        operands = [o.strip().strip("()") for o in e.split(" OR ")]
        cats = [classify(o)[0] for o in operands]
        for preferred in ("PERMISSIVE", "GPL_LINKING_EXCEPTION", "WEAK_FILE_COPYLEFT", "WEAK_LIB_COPYLEFT"):
            if preferred in cats:
                pick = operands[cats.index(preferred)]
                return preferred, f"dual licensed; {pick} taken from ({e})"
        return cats[0], f"dual licensed, no permissive option: {e}"

    # AND, or a single token: every operand's obligation applies, so the
    # strongest governs.
    tokens = [t.strip().strip("()") for t in re.split(r"\s+AND\s+", e)]
    ranked = []
    for t in tokens:
        if any(t.startswith(x) or x in t for x in GPL_WITH_LINKING_EXCEPTION):
            ranked.append(("GPL_LINKING_EXCEPTION", t))
        elif t in NETWORK_COPYLEFT:
            ranked.append(("NETWORK_COPYLEFT", t))
        elif t in STRONG_COPYLEFT:
            ranked.append(("STRONG_COPYLEFT", t))
        elif t in WEAK_LIB_COPYLEFT:
            ranked.append(("WEAK_LIB_COPYLEFT", t))
        elif t in WEAK_FILE_COPYLEFT:
            ranked.append(("WEAK_FILE_COPYLEFT", t))
        elif t in PROPRIETARY:
            ranked.append(("PROPRIETARY", t))
        elif t in PERMISSIVE:
            ranked.append(("PERMISSIVE", t))
        elif t.startswith("LicenseRef-"):
            ranked.append(("LICENSEREF", t))
        else:
            ranked.append(("UNRESOLVED", t))

    for cat, _ in CATEGORY_ORDER:
        for c, tok in ranked:
            if c == cat:
                if len(tokens) > 1:
                    return c, f"{tok} governs the expression ({e})"
                return c, tok
    return "UNRESOLVED", e


# ---------------------------------------------------------------------------
# Reading the repository
# ---------------------------------------------------------------------------
VAR = re.compile(r'^\s*(?P<k>[A-Z_]+(?::[a-zA-Z0-9_${}-]+)?)\s*(?:\??=|\+=|=\+|=)\s*"(?P<v>[^"]*)"')


def read_recipes() -> dict[str, dict]:
    """Every .bb in the SyMoNeuRaL layer, keyed by recipe name.

    A deliberately shallow parse: no bitbake, no variable expansion, no
    includes. It reads what a human reads. Where that is not enough the row is
    reported UNRESOLVED rather than guessed at, which is the whole contract of
    this tool.
    """
    out: dict[str, dict] = {}
    bbs: list[Path] = []
    for root in RECIPE_ROOTS:
        if root.exists():
            bbs.extend(sorted(root.rglob("*.bb")))
    for bb in bbs:
        name = bb.stem.split("_")[0]
        rec = {
            "recipe": name,
            "path": str(bb.relative_to(ROOT)) if str(bb).startswith(str(ROOT)) else str(bb),
            "license": "",
            "lic_files_chksum": "",
            "src_uri": "",
            "srcrev": "",
            "pv": "",
            "summary": "",
        }
        # A recipe's LICENSE is often in a required .inc rather than the .bb
        # itself (glibc, gcc and the Python stdlib all do this). Reading only the
        # .bb reports them as undeclared, which would be a false UNRESOLVED.
        texts = [bb.read_text(errors="replace")]
        for inc in re.findall(r"^\s*(?:require|include)\s+(\S+)", texts[0], re.M):
            for base in (bb.parent, *[r for r in RECIPE_ROOTS if r.exists()]):
                cands = [base / inc] if "/" in inc else list(base.rglob(inc))
                for c in cands[:3]:
                    try:
                        if c.is_file():
                            texts.append(c.read_text(errors="replace"))
                            break
                    except OSError:
                        pass
                else:
                    continue
                break
        for line in "\n".join(texts).splitlines():
            m = VAR.match(line)
            if not m:
                continue
            k, v = m.group("k"), m.group("v")
            if k == "LICENSE" and not rec["license"]:
                rec["license"] = v
            elif k == "LIC_FILES_CHKSUM" and not rec["lic_files_chksum"]:
                rec["lic_files_chksum"] = v
            elif k == "SRC_URI" and not rec["src_uri"]:
                rec["src_uri"] = v
            elif k == "SRCREV" and not rec["srcrev"]:
                rec["srcrev"] = v
            elif k == "PV" and not rec["pv"]:
                rec["pv"] = v
            elif k == "SUMMARY" and not rec["summary"]:
                rec["summary"] = v
        out[name] = rec
    return out


def read_manifests() -> dict[str, list[tuple[str, str, str]]]:
    """Package lists of root filesystems that were actually built.

    Format per line: `<name> <arch> <version>`, comments begin with #.
    """
    out: dict[str, list[tuple[str, str, str]]] = {}
    for man in sorted((ROOT / "production").glob("*/[A-Z]*INSTALL-MANIFEST.txt")):
        rows = []
        for line in man.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                rows.append((parts[0], parts[1], parts[2]))
        out[str(man.relative_to(ROOT))] = rows
    return out


def read_source_lock() -> dict[str, str]:
    """recipe_name -> recipe_LICENSE, as recorded at acquisition time.

    Used only to cross-check the recipes. Agreement is evidence; disagreement is
    reported rather than resolved, because a generator that silently picks a
    winner between two records destroys the reason for having two.
    """
    p = ROOT / "work" / "pins" / "source-lock.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    out = {}
    for c in data.get("components", []):
        rn, lic = c.get("recipe_name"), c.get("recipe_LICENSE")
        if rn and lic:
            out[rn] = lic
    return out


# Binary packages whose name gives no hint of the recipe that built them.
#
# OpenEmbedded splits and renames aggressively, and these are the renames that
# actually appear in this estate's image manifests. Each row was read off a
# manifest and traced to its recipe by hand; a guess here would defeat the tool,
# so anything not in this map and not matched by the rules below stays
# UNRESOLVED.
EXPLICIT_PACKAGE_MAP = {
    "libc6": "glibc", "libc-bin": "glibc", "ldconfig": "glibc",
    "libgcc1": "libgcc", "libgcc-s1": "libgcc",
    "libstdc++6": "gcc-runtime", "libgomp1": "gcc-runtime",
    "libatomic1": "gcc-runtime", "libitm1": "gcc-runtime",
    "libz1": "zlib", "libbz2-1": "bzip2", "liblzma5": "xz", "libzstd1": "zstd",
    "libssl4": "openssl", "libcrypto4": "openssl",
    "libtinfo5": "ncurses", "libncursesw5": "ncurses", "libpanelw5": "ncurses",
    "libformw5": "ncurses", "libmenuw5": "ncurses",
    "libuuid1": "util-linux", "libblkid1": "util-linux", "libmount1": "util-linux",
    "libsmartcols1": "util-linux", "libfdisk1": "util-linux",
    "util-linux-flock": "util-linux", "util-linux-libuuid": "util-linux",
    "libgdbm6": "gdbm", "libgdbm-compat4": "gdbm",
    "libsqlite3-0": "sqlite3", "libexpat1": "expat", "libffi8": "libffi",
    "libedit0": "libedit", "libyaml-0-2": "libyaml", "libreadline8": "readline",
    "libcap2": "libcap", "libcap-ng0": "libcap-ng", "libattr1": "attr", "libacl1": "acl",
    "libxcrypt1": "libxcrypt", "libcrypt2": "libxcrypt",
    "update-alternatives-opkg": "opkg-utils", "opkg-utils": "opkg-utils",
    "base-files": "base-files", "base-passwd": "base-passwd",
    "libpython3.14-1.0": "python3", "libpython3": "python3",
    "cuda-toolkit-bin": "symoneural-cuda-toolkit-bin",
}


def resolve_package(pkg: str, recipes: dict[str, dict]) -> tuple[str | None, str]:
    """Map a binary package name back to the recipe that produced it.

    OpenEmbedded splits a recipe into several binary packages and debian.bbclass
    renames a library package (symoneural-llm -> libsymoneural-llm0). Both are
    handled by trying the exact name, then stripping known split suffixes, then
    the debian shape. A name that survives all of that is UNRESOLVED, not
    assumed clean.
    """
    if pkg in recipes:
        return pkg, "exact recipe name"

    mapped = EXPLICIT_PACKAGE_MAP.get(pkg)
    if mapped and mapped in recipes:
        return mapped, f"explicit rename map -> {mapped}"

    # The Python stdlib ships as ~40 split packages (python3-core, python3-json,
    # python3-asyncio ...). All come from the one python3 recipe and share its
    # licence, so one rule covers the whole family rather than 40 map rows.
    if pkg.startswith("python3-") and "python3" in recipes:
        return "python3", "python3 stdlib split package"
    if pkg.startswith("python3") and "python3" in recipes:
        return "python3", "python3 package"

    for suffix in ("-dev", "-dbg", "-src", "-doc", "-staticdev", "-locale",
                   "-util", "-python", "-tools", "-bin", "-server", "-cuda"):
        if pkg.endswith(suffix):
            base = pkg[: -len(suffix)]
            if base in recipes:
                return base, f"split package of {base} ({suffix})"

    # debian.bbclass: libfoo0 / libfoo1.0 from recipe foo or libfoo
    m = re.match(r"^(lib.+?)[0-9][0-9.]*$", pkg)
    if m:
        for cand in (m.group(1), m.group(1)[3:]):
            if cand in recipes:
                return cand, f"debian-renamed package of {cand}"
            if f"symoneural-{cand}" in recipes:
                return f"symoneural-{cand}", f"debian-renamed package of symoneural-{cand}"

    if f"symoneural-{pkg}" in recipes:
        return f"symoneural-{pkg}", "symoneural- prefix added"

    return None, "not produced by a recipe in this layer"


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False).stdout.strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------
def audit() -> dict:
    recipes = read_recipes()
    manifests = read_manifests()
    lock = read_source_lock()

    # Every recipe in the layer, classified.
    layer_rows = []
    for name, rec in sorted(recipes.items()):
        cat, why = classify(rec["license"])
        row = dict(rec)
        row["category"] = cat
        row["reasoning"] = why
        locked = lock.get(name)
        row["source_lock_license"] = locked or ""
        row["agrees_with_source_lock"] = (
            "n/a" if not locked else ("yes" if locked == rec["license"] else "NO")
        )
        layer_rows.append(row)

    # What actually shipped, per built image.
    shipped: dict[str, list[dict]] = {}
    for man, rows in manifests.items():
        out = []
        for pkg, arch, ver in rows:
            rname, how = resolve_package(pkg, recipes)
            if rname:
                lic = recipes[rname]["license"]
                cat, why = classify(lic)
            else:
                lic, cat, why = "", "UNRESOLVED", how
            out.append({
                "package": pkg, "arch": arch, "version": ver,
                "recipe": rname or "", "resolution": how,
                "license": lic, "category": cat, "reasoning": why,
            })
        shipped[man] = out

    # Recipes carrying copyleft, and whether any of them shipped.
    copyleft_recipes = [r for r in layer_rows
                        if r["category"] in ("STRONG_COPYLEFT", "NETWORK_COPYLEFT",
                                             "WEAK_LIB_COPYLEFT", "WEAK_FILE_COPYLEFT")]
    shipped_recipe_names = {p["recipe"] for rows in shipped.values() for p in rows if p["recipe"]}
    for r in copyleft_recipes:
        r["shipped"] = r["recipe"] in shipped_recipe_names

    return {
        "schema": "symoneural-licence-audit/1",
        "generated_from": "the repository, on each run; this file is a rendering",
        "head": git_head(),
        "counts": {
            "recipes_in_layer": len(layer_rows),
            "manifests_read": len(manifests),
            "packages_shipped": sum(len(v) for v in shipped.values()),
        },
        "layer": layer_rows,
        "shipped": shipped,
        "copyleft_recipes": copyleft_recipes,
    }


def summarise(a: dict) -> tuple[list[str], bool]:
    """Human summary and the pass/fail verdict."""
    lines: list[str] = []
    ok = True

    by_cat: dict[str, list] = defaultdict(list)
    for r in a["layer"]:
        by_cat[r["category"]].append(r)

    lines.append(f"recipes in the layer: {a['counts']['recipes_in_layer']}")
    for cat, desc in CATEGORY_ORDER:
        n = len(by_cat.get(cat, []))
        if n:
            lines.append(f"  {n:4d}  {cat:<20s} {desc}")

    lines.append("")
    lines.append("SHIPPED, per built image manifest:")
    for man, rows in a["shipped"].items():
        cats: dict[str, int] = defaultdict(int)
        for p in rows:
            cats[p["category"]] += 1
        bad = {c: n for c, n in cats.items() if c in FAILING}
        verdict = "CLEAN" if not bad else "FAILS: " + ", ".join(f"{c}={n}" for c, n in sorted(bad.items()))
        if bad:
            ok = False
        lines.append(f"  {man}")
        lines.append(f"    {len(rows)} packages -> {verdict}")
        for c, n in sorted(cats.items()):
            lines.append(f"      {n:4d}  {c}")

    lines.append("")
    lines.append("COPYLEFT IN THE LAYER, and whether it reached an image:")
    if not a["copyleft_recipes"]:
        lines.append("  none")
    for r in sorted(a["copyleft_recipes"], key=lambda x: (not x["shipped"], x["recipe"])):
        flag = "SHIPPED" if r["shipped"] else "not shipped"
        lines.append(f"  {flag:<12s} {r['recipe']:<46s} {r['license']}")
        if r["shipped"] and r["category"] in ("STRONG_COPYLEFT", "NETWORK_COPYLEFT"):
            ok = False

    disagree = [r for r in a["layer"] if r["agrees_with_source_lock"] == "NO"]
    lines.append("")
    lines.append(f"recipe vs source-lock.json disagreements: {len(disagree)}")
    for r in disagree:
        lines.append(f"  {r['recipe']:<46s} recipe={r['license']!r} lock={r['source_lock_license']!r}")

    return lines, ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if copyleft ships or any shipped package is unresolved")
    ap.add_argument("--print", dest="print_only", action="store_true",
                    help="print the summary, write nothing")
    args = ap.parse_args()

    a = audit()
    lines, ok = summarise(a)
    print("\n".join(lines))

    if not args.print_only:
        outdir = ROOT / "production" / "licence"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "LICENCE-AUDIT.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
        (outdir / "LICENCE-AUDIT.txt").write_text("\n".join(lines) + "\n")
        print(f"\nwrote {outdir}/LICENCE-AUDIT.json and .txt")

    if args.check:
        print("\nVERDICT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
