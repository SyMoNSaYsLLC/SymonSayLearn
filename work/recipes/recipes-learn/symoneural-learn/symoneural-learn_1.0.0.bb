# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
# symoneural-learn: the glue that makes this build a product rather than a set of parts.
#
# Everything unique to the SymonSayLearn composition lives here and nowhere else:
# the bring-up scripts for the chat unit and
# the web interface, and the tracked client configuration. The runtimes themselves
# are separate packages; this is what arranges them.
#
# First-party, built from the committed tree by symoneural-firstparty, so ${S} is a
# `git archive` of what is COMMITTED. An uncommitted edit is not packaged, which is
# the property that makes a release reproducible from a tag.
SUMMARY = "SyMoNeuRaL SymonSayLearn composition - bring-up scripts"
DESCRIPTION = "Bring-up scripts for the SymonSayLearn runtime. Installs no weights and no \
credential."
HOMEPAGE = "https://symoneural.com"
LICENSE = "FSL-1.1-ALv2"
LIC_FILES_CHKSUM = "file://LICENSE;md5=f24be8021d54bb3ba168e56c716f6ee7"

inherit symoneural-firstparty
SYMON_FP_PATH = "work/runtimes/llm/hostrun"

# allarch: shell scripts and JSON. Nothing here is compiled, and a
# machine-specific package would force a rebuild per target for no reason.
inherit allarch

# The composition is useless without the surfaces it arranges, so they are runtime
# dependencies rather than a note in a document.
RDEPENDS:${PN} += " \
    symoneural-api-python \
    bash \
"

do_install() {
    install -d ${D}${libexecdir}/symoneural-learn
    install -m 0755 ${S}/serve-chat-unit.sh    ${D}${libexecdir}/symoneural-learn/serve-chat-unit
    install -m 0755 ${S}/bringup-chat-unit.sh  ${D}${libexecdir}/symoneural-learn/bringup-chat-unit

    # The identity travels with the package so an installed root can say which tree
    # it was built from without consulting anything else.
    install -d ${D}${datadir}/symoneural-learn
    install -m 0644 ${S}/SOURCE-TREE ${D}${datadir}/symoneural-learn/SOURCE-TREE

    # The terms travel with the runtime. LICENSE = "FSL-1.1-ALv2" is the SPDX token for the
    # Functional Source License (source-available, Apache-2.0 after two years); OE-core
    # ships its canonical text. Shipping the file is what makes the declaration checkable
    # on a target, and LIC_FILES_CHKSUM pins the exact Notice this build was made under.
    install -m 0644 ${S}/LICENSE ${D}${datadir}/symoneural-learn/LICENSE
}

FILES:${PN} = " \
    ${libexecdir}/symoneural-learn \
    ${datadir}/symoneural-learn \
"

# The bring-up scripts invoke an engine by path from the environment; they do not
# compile one in. The chat unit's engine is currently an ACQUIRED upstream build run
# from a host virtualenv, which rules section 3.10 governs as a recorded substitution
# and which this recipe therefore cannot package. Replacing it with an estate build
# is the next phase; when it lands, the engine becomes an RDEPENDS row here and the
# SYM_CHAT_ENGINE_VENV default disappears.
