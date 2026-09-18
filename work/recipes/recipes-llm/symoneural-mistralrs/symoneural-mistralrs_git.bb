# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
#
# The chat unit's next engine: a Rust inference server that loads the 20B MXFP4
# checkpoint natively, keeps the experts 4-bit on the GPU and speaks the Messages
# dialect itself. Selected by reports/rust-engine-eval-2026-09-18.md over three
# alternatives; the pin is work/pins/mistralrs-acquisition.json.
#
# Built by symoneural-pristine: a DISPOSABLE `git archive` export of the acquired tree.
# ${S} is throwaway; the acquired tree is never written to. do_unpack asserts the tree
# HEAD equals SRCREV and refuses to build otherwise. The patch below is applied to ${S}.
inherit symoneural-pristine
SYMON_TREE = "upstream/llm/engine/mistral.rs"

SUMMARY = "Rust inference engine for the chat unit (acquired)"
DESCRIPTION = "Serves the 20B MXFP4 checkpoint on the GPU and answers the Messages \
dialect on 127.0.0.1:8802 behind the first-party gateway. Replaces the recorded \
substitution engine (rules 3.10) once the first serve on this host is proven."
HOMEPAGE = "https://github.com/EricLBuehler/mistral.rs"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=2066570cad546d63de123046c2640c56"

SRC_URI = "git://github.com/EricLBuehler/mistral.rs;protocol=https;branch=master \
           file://0001-accept-the-13.4-cuda-toolkit.patch \
"
PV = "0.9.3"
SRCREV = "d5ae0f18f2170f10d30880cb7d21fb0880410e7b"

# Rust. cargo-update-recipe-crates writes the crate closure into ${THISDIR} so it is
# tracked in git rather than resolved from the network at build time. Not yet generated:
# run `bitbake -c update_crates symoneural-mistralrs` once a build directory exists, then
# add `require ${THISDIR}/symoneural-mistralrs-crates.inc`.
inherit cargo cargo-update-recipe-crates
inherit symoneural-cuda

CARGO_BUILD_FLAGS += "--features cuda -p mistralrs-cli"

# The GPU binding crate keeps its own toolkit allowlist with an environment override;
# the toolkit recipe is 13.4.1 and the nearest listed version is 13.3.
export CUDARC_CUDA_VERSION = "13030"
export CUDA_COMPUTE_CAP = "120"

# Sixteen MPL-2.0 crates are hard dependencies of the server binary (audio decode,
# web-search HTML parsing, directories). File-level weak copyleft, shipped unmodified —
# WEAK_COPYLEFT_FILE under the ship gate; each is listed in THIRD-PARTY-NOTICES.
