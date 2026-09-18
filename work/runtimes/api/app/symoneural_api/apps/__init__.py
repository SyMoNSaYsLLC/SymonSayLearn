# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""Application definitions. Each module registers ONE application with the
generic registry. Import this package to load every shipped definition; a new
demo is a new module here plus its first-party page content - nothing else."""
from . import dispatchos  # noqa: F401  (registers on import)
