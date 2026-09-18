# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
# symoneural-learn-web: the first-party web interface for the SymonSayLearn runtime.
#
# ============================================================================
# THIS RECIPE DOES NOT BUILD YET. THE BARRIER IS NAMED, NOT WORKED AROUND.
# ============================================================================
#
# Rules section 3.9 makes Next.js the frontend default and requires every framework
# to be acquired as pristine upstream source into the estate. Measured on disk,
# 2026-09-18:
#
#   upstream/web/runtime/workerd        the acquired workers runtime   acquired
#   upstream/web/tooling/workers-sdk    the acquired workers tooling   acquired
#   Next.js                                                       NOT acquired
#   React                                                         NOT acquired
#   Node.js                                                       NOT acquired
#
# There is no Node recipe anywhere in this layer, so there is no target interpreter
# to run a built Next.js application, and no acquired Next.js to build. The host
# build that exists today (work/runtimes/web/app/node_modules, 348 MB) came from the
# public npm registry, which is how Next.js is consumed but is NOT acquisition: the
# tree is not pinned in acquisition/, not committed, and not verifiable against an
# upstream commit.
#
# WHAT WOULD MAKE THIS BUILD, in order:
#   1. acquire Node.js as pristine source and add a recipe providing the target
#      interpreter (github.com/nodejs/node)
#   2. acquire Next.js and React at pinned commits (github.com/vercel/next.js,
#      github.com/facebook/react)
#   3. a symoneural-node.bbclass that runs an OFFLINE install from a vendored
#      store, the way symoneural-python handles Python wheels
#
# Until then this file exists so the shape is agreed and the gap is visible in the
# layer rather than only in a document. symoneural-image-learn deliberately does not
# install it; packagegroup-symoneural-learn lists it under RRECOMMENDS only.
#
# ============================================================================
SUMMARY = "SyMoNeuRaL web interface (Next.js) - BLOCKED on framework acquisition"
DESCRIPTION = "The first-party web interface for the SymonSayLearn runtime: the \
overview, model registry, rack view and the three surfaces. Serves on 127.0.0.1:8812 \
and reaches the gateway on 9001; no external origin appears in its configuration."
HOMEPAGE = "https://symoneural.com"
LICENSE = "FSL-1.1-ALv2"
LIC_FILES_CHKSUM = "file://LICENSE;md5=f24be8021d54bb3ba168e56c716f6ee7"

inherit symoneural-firstparty
SYMON_FP_PATH = "work/runtimes/web/app"

# The interface is a client of the gateway, not of the engine. It never talks to the
# chat unit directly, so the gateway is its only runtime edge.
RDEPENDS:${PN} += " \
    symoneural-api-python \
"

# Refuse in do_compile, NOT at parse time.
#
# The first version of this used an anonymous python block calling bb.fatal. That
# was wrong in a way worth recording: BitBake parses EVERY recipe in the layer on
# every build, so a parse-time fatal here would have failed every build in the
# estate, not just an attempt to build this package. A recipe that cannot be
# satisfied must still parse cleanly and fail only when someone asks for it.
do_compile() {
    bbfatal "symoneural-learn-web is blocked on framework acquisition.\n\
Next.js, React and Node.js are not acquired into this estate: upstream/web/ holds\n\
workerd and workers-sdk only, and no recipe provides a target Node interpreter.\n\
The header of this recipe lists the three acquisitions that unblock it.\n\
Build symoneural-image-learn instead; it excludes this package by design."
}

do_install() {
    :
}
