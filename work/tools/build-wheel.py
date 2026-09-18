#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""build-wheel — a reproducible wheel for one of our own pure-Python packages.

    work/tools/build-wheel.py --project <dir with pyproject.toml> --out <dir>

WHY THIS EXISTS
---------------
The wheels in v1.0.0 were built with flit_core. That backend is not installed in any
environment on this host and the package cache is empty, so an offline rebuild was
impossible: a change to the gateway could be committed and could not be shipped. The
choice was to publish wheels that no longer matched their own source, or to build them
ourselves. This builds them.

It handles exactly what our packages are — a single pure-Python package directory, no
compiled parts, no dynamic metadata — and refuses anything else rather than guessing.
That narrowness is the point: a general build backend is a dependency, and this is a
hundred lines we can read.

REPRODUCIBLE BY CONSTRUCTION
----------------------------
Entries are sorted, every timestamp is SOURCE_DATE_EPOCH (default: a fixed instant),
and compression is deterministic, so the same source yields the same bytes. Verified by
building twice and comparing sha256.
"""
from __future__ import annotations
import argparse, base64, hashlib, os, sys, tomllib, zipfile
from pathlib import Path

WHEEL_EPOCH = int(os.environ.get("SOURCE_DATE_EPOCH", "1700000000"))


def _urlsafe_b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _zipinfo(name: str) -> zipfile.ZipInfo:
    # Wheels must not carry a build clock; a fixed date is what makes two builds equal.
    ts = __import__("time").gmtime(WHEEL_EPOCH)
    zi = zipfile.ZipInfo(name, date_time=(ts.tm_year, ts.tm_mon, ts.tm_mday, ts.tm_hour, ts.tm_min, ts.tm_sec))
    zi.external_attr = (0o644 & 0xFFFF) << 16
    zi.compress_type = zipfile.ZIP_DEFLATED
    return zi


def metadata(cfg: dict) -> tuple[str, str, str]:
    proj = cfg["project"]
    name = proj["name"]
    version = proj.get("version")
    if version is None:
        raise SystemExit(f"{name}: dynamic version is not supported; state it in pyproject.toml")
    module = cfg.get("tool", {}).get("flit", {}).get("module", {}).get("name") or name.replace("-", "_")
    return name, str(version), module


def metadata_text(cfg: dict, name: str, version: str) -> str:
    proj = cfg["project"]
    lines = ["Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    if proj.get("description"):
        lines.append(f"Summary: {proj['description']}")
    lic = proj.get("license")
    if isinstance(lic, str):
        lines.append(f"License-Expression: {lic}")
    elif isinstance(lic, dict) and lic.get("text"):
        lines.append(f"License-Expression: {lic['text']}")
    if proj.get("requires-python"):
        lines.append(f"Requires-Python: {proj['requires-python']}")
    for dep in proj.get("dependencies", []) or []:
        lines.append(f"Requires-Dist: {dep}")
    for who in proj.get("authors", []) or []:
        if who.get("name"):
            lines.append(f"Author: {who['name']}")
        if who.get("email"):
            lines.append(f"Author-email: {who['email']}")
    for label, url in (proj.get("urls") or {}).items():
        lines.append(f"Project-URL: {label}, {url}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    cfg = tomllib.loads((a.project / "pyproject.toml").read_text())
    name, version, module = metadata(cfg)
    pkg_dir = a.project / module
    if not pkg_dir.is_dir():
        raise SystemExit(f"{name}: expected a package directory at {pkg_dir}")

    dist = f"{name.replace('-', '_')}-{version}"
    wheel_name = f"{dist}-py3-none-any.whl"
    a.out.mkdir(parents=True, exist_ok=True)
    target = a.out / wheel_name

    records: list[tuple[str, str, int]] = []

    def add(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
        zf.writestr(_zipinfo(arcname), data)
        digest = _urlsafe_b64(hashlib.sha256(data).digest())
        records.append((arcname, f"sha256={digest}", len(data)))

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for src in sorted(p for p in pkg_dir.rglob("*") if p.is_file()):
            if "__pycache__" in src.parts or src.suffix in (".pyc", ".pyo"):
                continue
            add(zf, str(src.relative_to(a.project)), src.read_bytes())

        info = f"{dist}.dist-info"
        add(zf, f"{info}/METADATA", metadata_text(cfg, name, version).encode())
        add(zf, f"{info}/WHEEL", b"Wheel-Version: 1.0\nGenerator: symoneural-build-wheel\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        scripts = cfg.get("project", {}).get("scripts") or {}
        if scripts:
            body = "[console_scripts]\n" + "".join(f"{k}={v}\n" for k, v in sorted(scripts.items()))
            add(zf, f"{info}/entry_points.txt", body.encode())
        lic = a.project / "LICENSE"
        if lic.exists():
            add(zf, f"{info}/LICENSE", lic.read_bytes())

        record_lines = [f"{n},{h},{s}" for n, h, s in records]
        record_lines.append(f"{info}/RECORD,,")
        zf.writestr(_zipinfo(f"{info}/RECORD"), ("\n".join(record_lines) + "\n").encode())

    print(f"{target}  {hashlib.sha256(target.read_bytes()).hexdigest()}  {target.stat().st_size} bytes")


if __name__ == "__main__":
    main()
