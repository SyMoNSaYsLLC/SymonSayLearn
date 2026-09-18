#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
#
# pack-release-trees — collapse each multi-file <unit>/<arch>/ tree into one archive.
#
#   work/tools/pack-release-trees.sh <stage> [--dry-run]
#
# WHY THIS EXISTS
# ---------------
# cut-release.sh turns EVERY file at depth two or greater into its own release asset.
# For a unit staged as a directory tree that is wrong three separate ways, all three
# measured against the v1.0.0 stage on 2026-09-18:
#
#   1. Name collisions. For a basename with no extension the cutter's renamer takes
#      stem and ext to be the same string, so `LICENSE` becomes
#      `LICENSE-linux-x86_64.LICENSE`. Four units each ship a LICENSE; 20 files
#      collapsed onto 9 names, so 11 assets could never land. The collision is
#      detected by GitHub after the tag has been created and pushed.
#   2. Dropped symlinks. The cutter enumerates with `find -type f`, which skips
#      symbolic links, so the soname chain (libsymoneural-api.so -> .so.1 ->
#      .so.1.0.0) loses its first two links and the library is unloadable by name.
#   3. Volume. Six trees would have uploaded as 57 separate assets.
#
# One archive per unit per architecture fixes all three. The archive is reproducible:
# entries sorted, a fixed timestamp, numeric owner 0:0, and gzip without its
# timestamp field, so the same input yields the same bytes.
#
# The original trees are MOVED, never deleted, and the destination is printed.
set -o pipefail

STAGE=${1:?stage directory, e.g. ~/symoneural-release/v1.0.0}
DRY=0; [ "${2:-}" = "--dry-run" ] && DRY=1
VER=$(basename "$STAGE")
KEEP=${SYM_TREE_KEEP:-$(dirname "$STAGE")/$VER-trees}
# The timestamp has to be fixed AND stable across reruns, which rules out anything the
# release process itself rewrites. An earlier version anchored it to SHIP-GATE-REPORT.json
# — but the gate rewrites that file on every run, so a repack after gating produced
# different bytes from the same input, silently breaking the reproducibility this flag set
# exists to provide. Each unit's BUILD-RECORD.md is written once when the unit is built and
# never touched again, so it is the stable anchor; SOURCE_DATE_EPOCH overrides it.
DEFAULT_EPOCH=${SOURCE_DATE_EPOCH:-}
unit_epoch() {  # $1 = unit directory
  [ -n "$DEFAULT_EPOCH" ] && { printf '%s' "$DEFAULT_EPOCH"; return; }
  if [ -f "$1/BUILD-RECORD.md" ]; then stat -c %Y "$1/BUILD-RECORD.md"; else echo 1700000000; fi
}

packed=0; skipped=0
for unit_dir in "$STAGE"/*/; do
  unit=$(basename "$unit_dir")
  for arch_dir in "$unit_dir"*/; do
    [ -d "$arch_dir" ] || continue
    arch=$(basename "$arch_dir")
    n=$(find "$arch_dir" -mindepth 1 \( -type f -o -type l \) | wc -l)
    if [ "$n" -le 1 ]; then
      printf '  skip   %-28s %-8s already a single artifact\n' "$unit" "$arch"
      skipped=$((skipped+1)); continue
    fi
    case "$arch" in noarch) name="$unit-${VER#v}-noarch.tar.gz";; *) name="$unit-${VER#v}-linux-$arch.tar.gz";; esac
    printf '  pack   %-28s %-8s %3s files -> %s\n' "$unit" "$arch" "$n" "$name"
    [ $DRY -eq 1 ] && { packed=$((packed+1)); continue; }

    tmp=$(mktemp -d) || exit 1
    EPOCH=$(unit_epoch "$unit_dir")
    # Archive from inside the arch directory so paths are relative to the unit, and
    # keep symlinks as symlinks: tar stores them, `find -type f` never saw them.
    tar --sort=name --mtime="@$EPOCH" --owner=0 --group=0 --numeric-owner \
        --format=gnu -cf "$tmp/x.tar" -C "$arch_dir" . ; rc=$?
    [ $rc -eq 0 ] || { echo "     tar rc=$rc"; exit 2; }
    gzip -n -9 "$tmp/x.tar"; rc=$?
    [ $rc -eq 0 ] || { echo "     gzip rc=$rc"; exit 2; }

    mkdir -p "$KEEP/$unit"
    mv "$arch_dir" "$KEEP/$unit/$arch"; rc=$?
    [ $rc -eq 0 ] || { echo "     move rc=$rc"; exit 3; }
    mkdir -p "$arch_dir"
    mv "$tmp/x.tar.gz" "$arch_dir$name"; rc=$?
    [ $rc -eq 0 ] || { echo "     place rc=$rc"; exit 3; }
    rmdir "$tmp" 2>/dev/null
    printf '         %s  %s\n' "$(sha256sum "$arch_dir$name" | cut -c1-16)" "$(stat -c %s "$arch_dir$name") bytes"
    packed=$((packed+1))
  done
done
echo
echo "packed $packed, skipped $skipped"
[ $DRY -eq 0 ] && [ $packed -gt 0 ] && echo "original trees moved to: $KEEP"
exit 0
