#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""ship-gate — the release gate, from every angle, run against the staged artifacts.

    ship-gate.py --stage /home/google/symoneural-release/v1.0.0 [--repo DIR ...] [--json OUT]

Exit 1 on any FAIL. It re-derives every census itself from the artifacts on disk — it
never trusts a build report. A scanner that is not installed is recorded as REVIEW,
never as a pass. The policy lives beside this file in ship-gate-policy.json; this
script only applies it.

Classes checked, per the policy: licence class of every component in every shipped
closure (wheels via a throwaway venv, web via package.json walk, ELF via NEEDED,
rootfs via license.manifest), attribution present in THIRD-PARTY-NOTICES, secrets by
content and by path (inside archives too), weights in artifacts, trademarks in
product-facing names, known CVEs, August-dated inputs, static-link copyleft.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, re, shutil, subprocess, sys, tarfile, tempfile, zipfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = json.loads((HERE / "ship-gate-policy.json").read_text())
CLASSES = POLICY["classes"]
ID2CLASS: dict[str, str] = {}
for cname, c in CLASSES.items():
    for i in c.get("ids", []):
        ID2CLASS.setdefault(i.lower(), cname)
NEUTRALISE = {e.lower() for e in CLASSES["STRONG_COPYLEFT"]["exceptions_that_neutralise"]}
USE_KW = [k.lower() for k in CLASSES["USE_RESTRICTED"].get("keywords", [])]
RANK = ["PERMISSIVE", "WEAK_COPYLEFT_FILE", "WEAK_COPYLEFT_LIB", "NUISANCE_CLAUSE", "PROPRIETARY_THIRD_PARTY",
        "USE_RESTRICTED", "UNKNOWN", "STRONG_COPYLEFT", "NETWORK_COPYLEFT"]
FAIL_CLASSES = {c for c, v in CLASSES.items() if v["verdict"] == "FAIL"}
EXC_COMPONENTS = {e["component"].lower(): e for e in POLICY.get("exceptions", [])}
FIRST_PARTY = {u.lower() for u in POLICY["first_party_units"]}
TRADEMARKS = re.findall(r"\((.*?)\)", POLICY["trademark_rule"])[0].split(", ")
SECRET_RX = {k: re.compile(v.encode()) for k, v in POLICY["secrets_patterns"].items()}
SECRET_PATH_RX = [re.compile(p) for p in POLICY.get("secret_file_paths", [])]
WEIGHT_EXT = tuple(POLICY["weights_extensions"])
BIG = POLICY["large_binary_review_bytes"]

# ----------------------------------------------------------------------------- SPDX
_norm = {"apache 2.0": "Apache-2.0", "apache-2": "Apache-2.0", "apache software license": "Apache-2.0", "apache license 2.0": "Apache-2.0",
         "apache license, version 2.0": "Apache-2.0", "mit license": "MIT", "the mit license": "MIT", "bsd": "BSD-3-Clause",
         "bsd license": "BSD-3-Clause", "new bsd": "BSD-3-Clause", "simplified bsd": "BSD-2-Clause", "isc license": "ISC",
         "mozilla public license 2.0": "MPL-2.0", "mpl 2.0": "MPL-2.0", "python software foundation license": "PSF-2.0",
         "psf": "PSF-2.0", "lgpl": "LGPL-2.1-or-later", "gpl": "GPL-2.0-or-later", "lgplv2.1": "LGPL-2.1-only", "lgplv3": "LGPL-3.0-only",
         "gplv2": "GPL-2.0-only", "gplv3": "GPL-3.0-only", "agplv3": "AGPL-3.0-only", "public domain": "public-domain",
         "unlicense": "Unlicense", "zlib/libpng": "Zlib", "0bsd": "0BSD", "bsd-3": "BSD-3-Clause", "bsd-2": "BSD-2-Clause",
         "apache-2.0 or mit": "Apache-2.0 OR MIT", "mit or apache-2.0": "MIT OR Apache-2.0", "mit/apache-2.0": "MIT OR Apache-2.0",
         "apache-2.0/mit": "Apache-2.0 OR MIT", "bsd-3-clause or mit": "BSD-3-Clause OR MIT", "mit or unlicense": "MIT OR Unlicense"}

def normalise(expr: str | None) -> str:
    if expr is None: return ""
    e = str(expr).strip()
    if e.lower() in _norm: return _norm[e.lower()]
    return e.replace("/", " OR ") if "/" in e and " " not in e else e

def classify_id(tok: str) -> str:
    t = tok.strip().strip("()").lower()
    if t.endswith("+"): t = t[:-1] + "-or-later"
    if t in ID2CLASS: return ID2CLASS[t]
    # families by prefix
    if t.startswith("agpl") or t.startswith("sspl") or t.startswith("osl-"): return "NETWORK_COPYLEFT"
    if t.startswith("lgpl-3") or t.startswith("gpl") or t.startswith("gfdl") or t.startswith("cc-by-sa"): return "STRONG_COPYLEFT"
    if t.startswith("lgpl"): return "WEAK_COPYLEFT_LIB"
    if t.startswith("mpl") or t.startswith("epl") or t.startswith("cddl"): return "WEAK_COPYLEFT_FILE"
    if t.startswith("cc-by-nc") or t.startswith("cc-by-nd") or "rail" in t or t.startswith("busl") or t.startswith("polyform") or t.startswith("fsl-") or t.startswith("llama"): return "USE_RESTRICTED"
    if t.startswith("bsd-4") or t == "json": return "NUISANCE_CLAUSE"
    if t.startswith("licenseref-nvidia") or t in ("proprietary", "unlicensed", "commercial"): return "PROPRIETARY_THIRD_PARTY"
    if t.startswith("cc-by") or t.startswith("bsd-") or t.startswith("mit") or t.startswith("apache") or t in ("isc", "zlib", "unlicense", "cc0-1.0", "0bsd", "psf-2.0", "python-2.0", "bsl-1.0", "ofl-1.1", "wtfpl", "blueoak-1.0.0"): return "PERMISSIVE"
    if t.startswith("licenseref-") or "custom" in t or "see license" in t: return "PROPRIETARY_THIRD_PARTY"
    return "UNKNOWN"

def classify(expr: str | None, *, static: bool = False, component: str = "") -> tuple[str, str]:
    """Return (class, reason) for an SPDX expression. OR → least restrictive; AND → most; WITH exception may neutralise."""
    e = normalise(expr)
    if not e or e.lower() in ("none", "null", "noassertion", "unknown"): return "UNKNOWN", "no licence expression"
    low = e.lower()
    for kw in USE_KW:
        if kw in low: return "USE_RESTRICTED", f"keyword '{kw}' in licence text"
    # tokenise: split on AND first (most restrictive governs), then OR inside (least restrictive wins)
    def rank(c): return RANK.index(c) if c in RANK else len(RANK)
    and_parts = re.split(r"\s+AND\s+|\s*&\s*", e, flags=re.I)
    worst, why = "PERMISSIVE", ""
    for part in and_parts:
        or_parts = re.split(r"\s+OR\s+|\s*\|\s*", part, flags=re.I)
        best, bwhy = None, ""
        for alt in or_parts:
            alt = alt.strip().strip("()")
            base, _, exc = alt.partition(" WITH ")
            c = classify_id(base)
            if exc and exc.strip().lower() in NEUTRALISE and c == "STRONG_COPYLEFT": c = "PERMISSIVE"
            if c == "WEAK_COPYLEFT_LIB" and static: c, alt = "STRONG_COPYLEFT", alt + " (statically linked)"
            if best is None or rank(c) < rank(best): best, bwhy = c, alt
        if rank(best) > rank(worst): worst, why = best, bwhy
    if component.lower() in EXC_COMPONENTS and worst in ("WEAK_COPYLEFT_LIB", "STRONG_COPYLEFT", "PROPRIETARY_THIRD_PARTY"):
        return "PERMISSIVE", f"recorded exception: {EXC_COMPONENTS[component.lower()]['why_it_passes']}"
    return worst, why or e

# ----------------------------------------------------------------------------- report
class Report:
    def __init__(self): self.units: dict[str, dict] = {}; self.cross: list[dict] = []
    def unit(self, name):
        return self.units.setdefault(name, {"components": [], "findings": [], "artifacts": [], "verdict": "PASS"})
    def finding(self, unit, level, kind, detail):
        u = self.unit(unit); u["findings"].append({"level": level, "kind": kind, "detail": detail})
        if level == "FAIL": u["verdict"] = "FAIL"
        elif level == "REVIEW" and u["verdict"] == "PASS": u["verdict"] = "REVIEW"
    def component(self, unit, name, version, licence, klass, reason, source):
        self.unit(unit)["components"].append({"name": name, "version": version, "license": licence, "class": klass, "reason": reason, "source": source})
        if klass in FAIL_CLASSES or klass == "PROPRIETARY_THIRD_PARTY":
            self.finding(unit, "FAIL", f"licence:{klass}", f"{name} {version}: {licence} — {reason}")

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def run(cmd, **kw):
    t0 = time.time(); r = subprocess.run(cmd, capture_output=True, text=True, **kw); return r.returncode, r.stdout, r.stderr, round(time.time() - t0, 1)

# ----------------------------------------------------------------------------- censuses
def census_wheel(rep: Report, unit: str, whl: Path, tmp: Path):
    venv = tmp / f"venv-{unit}"; rc, out, err, s = run([sys.executable, "-m", "venv", str(venv)])
    if rc: return rep.finding(unit, "REVIEW", "census", f"venv creation failed rc={rc}: {err[-300:]}")
    py = venv / "bin" / "python"
    rc, out, err, s = run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", str(whl)])
    if rc: return rep.finding(unit, "FAIL", "install", f"pip install {whl.name} rc={rc}: {(err or out)[-600:]}")
    rep.finding(unit, "INFO", "install", f"pip install {whl.name} rc=0 in {s}s")
    code = r'''
import json, importlib.metadata as m
rows=[]
for d in m.distributions():
    md=d.metadata; lic=md.get("License-Expression") or md.get("License") or ""
    if not lic or len(lic)>200 or "\n" in lic:
        cls=[c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
        lic=" AND ".join(cls) if cls else (lic[:60] if lic else "")
    rows.append({"name":md["Name"],"version":md["Version"],"license":lic})
print(json.dumps(rows))'''
    rc, out, err, s = run([str(py), "-I", "-c", code])
    if rc: return rep.finding(unit, "REVIEW", "census", f"metadata read failed: {err[-300:]}")
    for r in json.loads(out):
        if r["name"].lower() in ("pip", "setuptools", "wheel"): continue
        fp = r["name"].lower().replace("_", "-") in FIRST_PARTY
        k, why = ("PERMISSIVE", "first-party") if fp else classify(r["license"], component=r["name"])
        rep.component(unit, r["name"], r["version"], r["license"], k, why, "importlib.metadata in throwaway venv")
    # bundled native libs inside the wheel → static rule
    with zipfile.ZipFile(whl) as z:
        sos = [n for n in z.namelist() if n.endswith(".so") or ".so." in n]
    if sos: rep.finding(unit, "REVIEW", "static", f"wheel bundles native libs {sos[:5]} — their closure must be checked as static")
    # CVEs
    rc, out, err, s = run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", "pip-audit"])
    if rc: return rep.finding(unit, "REVIEW", "cve", "pip-audit unavailable (install failed) — not a pass")
    rc, out, err, s = run([str(py), "-m", "pip_audit", "--format", "json", "--progress-spinner", "off"])
    try: vulns = json.loads(out).get("dependencies", [])
    except Exception: return rep.finding(unit, "REVIEW", "cve", f"pip-audit output unreadable rc={rc}: {err[-200:]}")
    bad = [(d["name"], v["id"], v.get("fix_versions")) for d in vulns for v in d.get("vulns", [])]
    if bad: rep.finding(unit, "FAIL", "cve", f"known vulnerabilities: {bad[:10]}")
    else: rep.finding(unit, "INFO", "cve", f"pip-audit: 0 known vulnerabilities across {len(vulns)} dists")

def census_node_tree(rep: Report, unit: str, root: Path):
    seen = {}
    for pj in root.rglob("package.json"):
        try: d = json.loads(pj.read_text(encoding="utf-8", errors="replace"))
        except Exception: continue
        name, ver = d.get("name"), d.get("version")
        if not name or not ver: continue
        lic = d.get("license") or d.get("licenses")
        if isinstance(lic, list): lic = " OR ".join(x.get("type", str(x)) if isinstance(x, dict) else str(x) for x in lic)
        if isinstance(lic, dict): lic = lic.get("type")
        seen[(name, ver)] = lic or ""
    for (name, ver), lic in sorted(seen.items()):
        fp = name.lower() in FIRST_PARTY or name.lower().startswith("symoneural")
        k, why = ("PERMISSIVE", "first-party") if fp else classify(lic, component=name)
        rep.component(unit, name, ver, lic, k, why, f"package.json walk under {root.name}")
    rep.finding(unit, "INFO", "census", f"{len(seen)} node packages enumerated")

def census_elf(rep: Report, unit: str, elf: Path, static_meta: Path | None):
    rc, out, err, s = run(["readelf", "-d", str(elf)])
    needed = re.findall(r"Shared library: \[(.+?)\]", out)
    rep.finding(unit, "INFO", "linkage", f"{elf.name}: NEEDED={needed or 'none (static)'}")
    for lib in needed:
        rc, o, e, s = run(["bash", "-c", f"dpkg -S \"$(ldconfig -p | awk '$1==\"{lib}\"{{print $NF; exit}}')\" 2>/dev/null | cut -d: -f1"])
        pkg = o.strip() or lib
        lic = ""
        cp = Path(f"/usr/share/doc/{pkg}/copyright")
        if cp.exists():
            m = re.findall(r"^License:\s*(.+)$", cp.read_text(errors="replace"), flags=re.M)
            lic = " AND ".join(sorted(set(x.strip() for x in m if x.strip()))) if m else ""
        comp = "glibc" if pkg.startswith("libc6") else ("libgcc / libstdc++ / libgomp" if pkg.startswith(("libgcc", "libstdc++", "libgomp")) else pkg)
        k, why = classify(lic or "UNKNOWN", component=comp)
        rep.component(unit, lib, pkg, lic, k, why, "readelf NEEDED → dpkg → debian/copyright")
    if static_meta and static_meta.exists():
        meta = json.loads(static_meta.read_text())
        for p in meta.get("packages", []):
            k, why = classify(p.get("license"), static=True, component=p["name"])
            rep.component(unit, p["name"], p["version"], p.get("license"), k, why, f"cargo metadata (static closure) {static_meta.name}")
    elif not needed or len(needed) < 4:
        rep.finding(unit, "REVIEW", "static", f"{elf.name} looks statically linked and no cargo-metadata.json sits beside it — static closure census missing")

def census_manifest(rep: Report, unit: str, manifest: Path):
    cur = {}
    for line in manifest.read_text(errors="replace").splitlines():
        if line.startswith("PACKAGE NAME:"): cur = {"name": line.split(":", 1)[1].strip()}
        elif line.startswith("PACKAGE VERSION:"): cur["version"] = line.split(":", 1)[1].strip()
        elif line.startswith("LICENSE:"):
            cur["license"] = line.split(":", 1)[1].strip()
            comp = "glibc" if cur["name"].startswith(("libc6", "glibc", "ldconfig", "libc-")) else ("libgcc / libstdc++ / libgomp" if cur["name"].startswith(("libgcc", "libstdc++", "libgomp")) else cur["name"])
            k, why = classify(cur["license"], component=comp)
            rep.component(unit, cur["name"], cur.get("version", ""), cur["license"], k, why, manifest.name)

# ----------------------------------------------------------------------------- cross-cutting
def scan_bytes(rep, unit, label, data: bytes):
    for name, rx in SECRET_RX.items():
        for m in rx.finditer(data):
            rep.finding(unit, "FAIL", "secret", f"{label}: pattern {name}, fingerprint {hashlib.sha256(m.group(0)).hexdigest()[:12]} (value withheld)")

_TM_REVIEW: dict[str, set] = {}

def scan_path_rules(rep, unit, label, *, top=False):
    """Secret-file names and weights fail anywhere. A third-party mark fails only in a TOP-LEVEL artifact
    name (that is what we ship under our name); inside an archive it is a dependency name → one REVIEW."""
    if any(r.search(label) for r in SECRET_PATH_RX): rep.finding(unit, "FAIL", "secret-file", f"{label}: path matches a secret-file rule")
    if label.endswith(WEIGHT_EXT): rep.finding(unit, "FAIL", "weights", f"{label}: model weights inside an artifact")
    low = Path(label.split("!")[-1]).name.lower()
    if low.startswith("symoneural"): return
    for tm in TRADEMARKS:
        if re.search(rf"\b{re.escape(tm)}\b", low):
            if top: rep.finding(unit, "FAIL", "trademark", f"{label}: third-party mark '{tm}' in an artifact name")
            else: _TM_REVIEW.setdefault(unit, set()).add(f"{tm}:{low}")

def flush_trademark_reviews(rep):
    for unit, hits in _TM_REVIEW.items():
        rep.finding(unit, "REVIEW", "trademark", f"{len(hits)} dependency/member names carry a third-party mark (not failed): {sorted(hits)[:8]}{' …' if len(hits) > 8 else ''}")

def scan_archive(rep, unit, path: Path):
    scan_path_rules(rep, unit, str(path), top=True); scan_bytes(rep, unit, path.name, path.read_bytes() if path.stat().st_size < BIG else b"")
    if path.stat().st_size >= BIG: rep.finding(unit, "REVIEW", "size", f"{path.name}: {path.stat().st_size} bytes — large binary; content scan skipped, contents listed")
    members = []
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                for i in z.infolist():
                    members.append((i.filename, i.file_size)); scan_path_rules(rep, unit, f"{path.name}!{i.filename}")
                    if i.file_size < 20 << 20: scan_bytes(rep, unit, f"{path.name}!{i.filename}", z.read(i))
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as t:
                for m in t:
                    if not m.isfile(): continue
                    members.append((m.name, m.size)); scan_path_rules(rep, unit, f"{path.name}!{m.name}")
                    if m.size < 20 << 20: scan_bytes(rep, unit, f"{path.name}!{m.name}", t.extractfile(m).read())
                    elif m.size >= BIG: rep.finding(unit, "REVIEW", "size", f"{path.name}!{m.name}: {m.size} bytes inside archive — check it is not weights")
    except Exception as ex:
        rep.finding(unit, "REVIEW", "archive", f"{path.name}: could not open ({ex})")
    return members

def check_august(rep, unit, path: Path):
    mt = time.strftime("%Y-%m", time.gmtime(path.stat().st_mtime))
    if mt == "2026-08": rep.finding(unit, "FAIL", "august", f"{path.name} mtime is August 2026")
    if path.suffix in (".md", ".json", ".txt"):
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if "2026-08" in line and not re.search(r"rule|bars|predates|fresh start|section 3\.2", line, re.I):
                rep.finding(unit, "FAIL", "august", f"{path.name}:{i} carries an August 2026 date")

def check_attribution(rep, notices: Path | None):
    text = notices.read_text(errors="replace").lower() if notices and notices.exists() else ""
    for unit, u in rep.units.items():
        missing = sorted({c["name"] for c in u["components"] if c["class"] in ("PERMISSIVE", "WEAK_COPYLEFT_FILE", "WEAK_COPYLEFT_LIB")
                          and c["reason"] != "first-party" and c["name"].lower() not in text})
        if not text: rep.finding(unit, "FAIL", "attribution", "THIRD-PARTY-NOTICES.md missing — attribution owed for every permissive component")
        elif missing: rep.finding(unit, "FAIL", "attribution", f"{len(missing)} components absent from THIRD-PARTY-NOTICES: {missing[:12]}{' …' if len(missing) > 12 else ''}")

def check_repo_history(rep, repo: Path):
    unit = f"repo:{repo.resolve().name}"
    rc, out, err, s = run(["git", "-C", str(repo), "rev-list", "--objects", "--all"])
    if rc: return rep.finding(unit, "REVIEW", "repo", f"not a git repo or unreadable: {err[-200:]}")
    n = 0
    for line in out.splitlines():
        sha, _, path = line.partition(" ")
        if not path: continue
        t = subprocess.run(["git", "-C", str(repo), "cat-file", "-t", sha], capture_output=True, text=True).stdout.strip()
        if t != "blob": continue
        n += 1; scan_path_rules(rep, unit, path)
        data = subprocess.run(["git", "-C", str(repo), "cat-file", "-p", sha], capture_output=True).stdout
        if len(data) > BIG: rep.finding(unit, "FAIL", "size", f"{path}: {len(data)} bytes in history — weights or build output")
        scan_bytes(rep, unit, f"{path}@{sha[:9]}", data)
    rc, out, err, s = run(["git", "-C", str(repo), "log", "--format=%ci"])
    if any(l.startswith("2026-08") for l in out.splitlines()): rep.finding(unit, "FAIL", "august", "commits dated August 2026 in history")
    rep.finding(unit, "INFO", "repo", f"{n} blobs scanned across all refs")

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, help="staged release dir: <unit>/<arch>/<files>")
    ap.add_argument("--repo", type=Path, action="append", default=[], help="git repo(s) whose full history is scanned before push")
    ap.add_argument("--notices", type=Path, help="THIRD-PARTY-NOTICES.md (default: <stage>/THIRD-PARTY-NOTICES.md)")
    ap.add_argument("--json", type=Path, help="write the full report here")
    ap.add_argument("--keep-tmp", action="store_true")
    a = ap.parse_args()
    rep = Report(); tmp = Path(tempfile.mkdtemp(prefix="ship-gate-", dir=os.environ.get("CLAUDE_JOB_DIR", "/tmp") + "/tmp" if os.environ.get("CLAUDE_JOB_DIR") else None))
    try:
        if a.stage and a.stage.exists():
            for unit_dir in sorted(p for p in a.stage.iterdir() if p.is_dir()):
                unit = unit_dir.name
                for f in sorted(unit_dir.rglob("*")):
                    if not f.is_file(): continue
                    rel = f.relative_to(a.stage); arch = rel.parts[1] if len(rel.parts) > 2 else "-"
                    rep.unit(unit)["artifacts"].append({"path": str(rel), "arch": arch, "sha256": sha256(f), "bytes": f.stat().st_size})
                    check_august(rep, unit, f)
                    if f.suffix == ".whl": census_wheel(rep, unit, f, tmp); scan_archive(rep, unit, f)
                    elif f.name == "license.manifest": census_manifest(rep, unit, f)
                    elif f.suffix in (".gz", ".xz", ".bz2", ".zst", ".tar", ".zip", ".tgz"):
                        members = scan_archive(rep, unit, f)
                        if any(m[0].endswith("package.json") for m in members) and f.stat().st_size < 2 << 30:
                            d = tmp / f"x-{unit}-{f.stem}"; d.mkdir(exist_ok=True)
                            try:
                                with tarfile.open(f) as t: t.extractall(d, filter="data")
                                census_node_tree(rep, unit, d)
                            except Exception as ex: rep.finding(unit, "REVIEW", "census", f"could not extract {f.name} for node census: {ex}")
                    elif f.stat().st_size > 0 and f.open("rb").read(4) == b"\x7fELF":
                        census_elf(rep, unit, f, f.parent / "cargo-metadata.json"); scan_path_rules(rep, unit, str(rel), top=True)
                    else:
                        scan_path_rules(rep, unit, str(rel), top=True)
                        if f.stat().st_size < BIG: scan_bytes(rep, unit, str(rel), f.read_bytes())
                if not rep.unit(unit)["components"] and unit not in ("source", "symoneural-learn-hostrun"):
                    rep.finding(unit, "REVIEW", "census", "no dependency census could be derived for this unit — licence closure UNESTABLISHED")
            flush_trademark_reviews(rep)
            check_attribution(rep, a.notices or (a.stage / "THIRD-PARTY-NOTICES.md"))
        for r in a.repo: check_repo_history(rep, r)
    finally:
        if not a.keep_tmp: shutil.rmtree(tmp, ignore_errors=True)
    # ---- print
    overall = "PASS"
    for unit, u in rep.units.items():
        fails = [f for f in u["findings"] if f["level"] == "FAIL"]; reviews = [f for f in u["findings"] if f["level"] == "REVIEW"]
        by = {}
        for c in u["components"]: by[c["class"]] = by.get(c["class"], 0) + 1
        print(f"\n== {unit}: {u['verdict']}   components={len(u['components'])} {dict(sorted(by.items()))}  artifacts={len(u['artifacts'])}")
        for f in fails: print(f"   FAIL    {f['kind']:<22} {f['detail']}")
        for f in reviews: print(f"   REVIEW  {f['kind']:<22} {f['detail']}")
        if u["verdict"] == "FAIL": overall = "FAIL"
        elif u["verdict"] == "REVIEW" and overall == "PASS": overall = "REVIEW"
    print(f"\nSHIP GATE: {overall}")
    if a.json:
        a.json.write_text(json.dumps({"overall": overall, "policy": POLICY["schema"], "units": rep.units}, indent=1))
        print(f"report: {a.json}")
    sys.exit(1 if overall == "FAIL" else 0)

if __name__ == "__main__":
    main()
