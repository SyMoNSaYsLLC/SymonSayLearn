# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
# Drop gdbm from python3.
#
# gdbm is GPL-3.0-only and reaches the image ONLY because OpenEmbedded's python3
# recipe enables it by default:
#
#     PACKAGECONFIG ??= "editline gdbm ${@bb.utils.filter('DISTRO_FEATURES', 'lto', d)}"
#
# It brings libgdbm6, libgdbm-compat4 and python3-gdbm with it. Measured: nothing in
# this estate imports dbm, shelve or _gdbm — grep over work/runtimes, work/tools and
# production returns nothing. So the capability is dropped rather than the licence
# policy bent.
#
# What this costs: the _gdbm and _dbm C modules both go (the recipe disables them
# together). dbm.dumb is pure Python and remains, so `shelve` still works. Anything
# wanting a real key-value store should use sqlite3, which already ships and whose
# licence is `blessing` — SQLite's public-domain dedication.
#
# THIS BELONGS IN A BBAPPEND, NOT IN THE IMAGE RECIPE. An image recipe's variables
# apply to the image, not to other recipes; a PACKAGECONFIG:remove:pn-python3 line
# there parses cleanly and has no effect, which looks enforced while enforcing
# nothing.
PACKAGECONFIG:remove = "gdbm"
