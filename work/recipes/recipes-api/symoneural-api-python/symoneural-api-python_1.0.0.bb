# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
# symoneural_api: the generic Python API (FastAPI service, application registry,
# demo policy, unit supervisor binding, ctypes binding to libsymoneural-api).
# First-party, built from HEAD:Symoneural-API/app by symoneural-firstparty.
#
# RDEPENDS follow pyproject [project].dependencies exactly as
# tools/check-python-runtime-closures.py --runtime API evaluates them; the
# native library is a runtime dependency because symoneural_api.native loads
# libsymoneural-api.so.1 (with a recorded Python fallback when absent).
SUMMARY = "SyMoNeuRaL API - generic control plane and application layer (Python)"
HOMEPAGE = "https://symoneural.com"
LICENSE = "FSL-1.1-ALv2"
LIC_FILES_CHKSUM = "file://LICENSE;md5=f24be8021d54bb3ba168e56c716f6ee7"

inherit symoneural-firstparty python_flit_core
SYMON_FP_PATH = "work/runtimes/api/app"

RDEPENDS:${PN} += " \
    symoneural-fastapi \
    symoneural-pydantic \
    symoneural-uvicorn \
    symoneural-api \
    python3-ctypes \
    python3-json \
    python3-logging \
    python3-asyncio \
"
