# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
# The SymonSayLearn runtime: ONE deployable surface for this whole build.
#
# Every other packagegroup in this directory is a SLICE of the estate - one runtime,
# one unit, one closure. This one is the COMPOSITION: the set a person installs to
# get the product that has been built here, rather than a component of it. It is the
# thing that gets a version number and a GitHub release.
#
# It names other packagegroups, not their members. An installed set that re-lists
# what another group already declares drifts the moment that group changes, and then
# two files disagree about one closure. Adding a package to the LLM runtime must
# reach this runtime without anyone editing this file.
#
# WHAT THIS RUNTIME IS
#
#   the /v1 dialect gateway on 127.0.0.1:9001      symoneural-api-python
#   the chat unit behind it on 127.0.0.1:8802      packagegroup-symoneural-llm
#   the web interface on 127.0.0.1:8812            symoneural-learn-web
#   the bring-up scripts, units and config         symoneural-learn
#
# WHAT IT IS NOT
#
#   Weights. Nothing here installs a model. The runtime reads SYM_MODELS_DIR at run
#   time, $HOME/symoneural-models by default. Weights are licensed
#   separately, are multiple gigabytes, and never enter a package or git.
#
#   A credential. The gateway reads its key from a 0600 file the operator provisions.
#   A package that shipped a secret would ship the same secret to everyone.
SUMMARY = "SyMoNeuRaL SymonSayLearn runtime - gateway, chat unit and web interface"
DESCRIPTION = "The composed runtime for this build: the Messages-dialect gateway, \
the chat unit it fronts, and the first-party web interface, with the scripts and \
units that bring them up. Models and credentials are external by design."
LICENSE = "MIT"
inherit packagegroup

# The slices this runtime is composed of. Each is a packagegroup in this directory.
RDEPENDS:${PN} = " \
    packagegroup-symoneural-api \
    packagegroup-symoneural-llm \
    packagegroup-symoneural-common \
    symoneural-learn \
"

# Optional slices. RRECOMMENDS rather than RDEPENDS because the runtime serves
# without them: the gateway and chat unit answer with no web interface present, and
# an image that refuses to build because an optional surface is missing is a worse
# failure than one that ships without it.
#
# NOTE: the image sets NO_RECOMMENDATIONS, so an image that wants these must name
# them in IMAGE_INSTALL. That is deliberate - a proof image records exactly what it
# installed, and a recommendation that silently lands in a clean root defeats it.
RRECOMMENDS:${PN} = " \
    symoneural-learn-web \
    packagegroup-symoneural-cli \
"
