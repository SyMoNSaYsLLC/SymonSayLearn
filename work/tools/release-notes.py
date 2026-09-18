#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""release-notes — RELEASE-NOTES.md from the gate report and the build records, never from memory.

    work/tools/release-notes.py --stage <stage> --tag v1.0.0 --out <stage>/RELEASE-NOTES.md

What a reader of a release needs is not a changelog. It is: what is in it, what
architecture each piece runs on, what was actually exercised rather than merely built,
and what the gate still wants a human to look at. All four come from files in the stage
— SHIP-GATE-REPORT.json and each unit's BUILD-RECORD.md — so the notes cannot drift from
the artifacts they describe. A unit that was built but never run says so.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

def human(n: int) -> str:
    """A size a reader can act on: a 22 kB wheel and a 62 MB library are not both '0.0 MB'."""
    for unit, step in (("GB", 1 << 30), ("MB", 1 << 20), ("kB", 1 << 10)):
        if n >= step:
            return f"{n/step:.1f} {unit}"
    return f"{n} B"

def build_record(stage: Path, unit: str) -> dict:
    """Pull the few facts we publish out of a unit's build record."""
    p = stage / unit / "BUILD-RECORD.md"
    out: dict[str, str] = {}
    if not p.exists():
        return out
    text = p.read_text(errors="replace")
    m = re.search(r"source:\s*(\S+)\s*@\s*([0-9a-f]{7,40})", text)
    if m:
        out["source"] = m.group(1)
        out["commit"] = m.group(2)[:12]
    if re.search(r"sha256 identical:\s*yes", text, re.I):
        out["reproducible"] = "yes"
    elif re.search(r"built twice", text, re.I):
        out["reproducible"] = "attempted"
    m = re.search(r"exercised[^.\n]*", text, re.I)
    if m:
        out["exercised"] = m.group(0).strip()[:80]
    return out

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    out = a.out or (a.stage / "RELEASE-NOTES.md")
    rep = json.loads((a.stage / "SHIP-GATE-REPORT.json").read_text())
    units = rep.get("units", {})

    assets: dict[str, list[tuple[str, str, int]]] = {}
    for unit, u in units.items():
        for art in u.get("artifacts", []):
            path = art.get("path", "")
            name = path.rsplit("/", 1)[-1]
            if name in ("BUILD-RECORD.md", "SHA256SUMS", "cargo-metadata.json"):
                continue
            assets.setdefault(unit, []).append((name, art.get("arch", "-"), art.get("bytes", 0)))

    L: list[str] = []
    L += [f"# SyMoNsAyLeaRn {a.tag}", "",
          "SyMoNeuRaL's own runtimes, built from pristine upstream source. Licensed under",
          "FSL-1.1-ALv2: source-available now, Apache-2.0 two years after this release. See",
          "`LICENSE`, and `THIRD-PARTY-NOTICES.md` for every third-party component the",
          "artifacts actually contain.", ""]

    L += ["## What is in this release", "",
          "| Unit | Architecture | Asset | Size |", "|---|---|---|---|"]
    total = 0
    for unit in sorted(assets):
        for name, arch, size in sorted(assets[unit]):
            total += size
            L.append(f"| `{unit}` | {arch} | `{name}` | {human(size)} |")
    L += ["", f"{sum(len(v) for v in assets.values())} assets, {total/1048576:.0f} MB in total.", ""]

    L += ["## Provenance", "",
          "| Unit | Source commit | Reproducible | Exercised |", "|---|---|---|---|"]
    for unit in sorted(assets):
        r = build_record(a.stage, unit)
        L.append(f"| `{unit}` | `{r.get('commit','—')}` | {r.get('reproducible','not claimed')} | {r.get('exercised','not stated')} |")
    L += ["",
          "\"Reproducible\" means the unit was built twice from two independent exports and the",
          "bytes matched. \"Exercised\" is what a consumer actually ran; a unit that was built",
          "but never run says so rather than implying otherwise.", ""]

    verdicts = {u: d.get("verdict", "?") for u, d in units.items()}
    n_review = sum(1 for v in verdicts.values() if v == "REVIEW")
    n_fail = sum(1 for v in verdicts.values() if v == "FAIL")
    L += ["## Ship gate", "",
          f"Overall **{rep.get('overall','?')}** under policy `{rep.get('policy','?')}` — "
          f"{n_fail} failing unit(s), {n_review} needing review.", "",
          "The gate classifies every component by licence, and separately looks for secrets by",
          "content and by path, weights, trademarks, known vulnerabilities and identifiers. A",
          "FAIL blocks the release. A REVIEW does not, and every one of them is listed here so",
          "that shipping with it is a decision rather than an oversight.", ""]
    if n_review:
        L += ["| Unit | What the gate wants looked at |", "|---|---|"]
        for unit in sorted(units):
            rs = [f for f in units[unit].get("findings", []) if f.get("level") == "REVIEW"]
            if not rs:
                continue
            kinds: dict[str, int] = {}
            for f in rs:
                kinds[f.get("kind", "?")] = kinds.get(f.get("kind", "?"), 0) + 1
            L.append(f"| `{unit}` | " + ", ".join(f"{k} ×{v}" if v > 1 else k for k, v in sorted(kinds.items())) + " |")
        L.append("")

    L += ["## Installing", "",
          "```sh",
          "git clone https://github.com/SyMoNSaYsLLC/symoneural-learn.git && cd symoneural-learn",
          "tools/install-from-release.sh --dry-run          # what would happen on this machine",
          f"tools/install-from-release.sh --release {a.tag}   # verified against SHA256SUMS first",
          "```", "",
          "Every asset is checked against `SHA256SUMS` before anything is installed; a single",
          "mismatch stops the run. `tools/verify-3p-path.sh` then exercises the installed",
          "deployment end to end.", ""]
    out.write_text("\n".join(L))
    print(f"wrote {out} — {sum(len(v) for v in assets.values())} assets, {len(units)} units, overall {rep.get('overall')}")

if __name__ == "__main__":
    main()
