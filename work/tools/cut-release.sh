#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
#
# cut-release — publish a staged release to GitHub, but only if the ship gate passes.
#
#   tools/cut-release.sh v1.0.0 /home/google/symoneural-release/v1.0.0 [--dry-run] [--prerelease]
#
# What it enforces, in order, each with its own exit code check:
#   1. the tag names a commit that exists locally and equals HEAD (a release is a commit)
#   2. the stage carries SHA256SUMS, RELEASE-NOTES.md, THIRD-PARTY-NOTICES.md, and every sum verifies
#   3. tools/ship-gate.py --stage <stage> --repo . exits 0 — every licence class, secrets, weights,
#      trademarks, CVEs, August dates, attribution
#   4. asset names carry the architecture: <unit>-<version>-linux-<arch>.<ext> or <unit>-<version>-noarch.<ext>
#      (files staged under <unit>/<arch>/ are renamed on upload if the name lacks the arch)
#   5. gh release create <tag> with the notes as the body and every asset attached; GitHub adds the
#      source tarball itself. A pre-existing release of that tag aborts — releases are immutable here.
# Nothing is uploaded on a dry run; the exact gh command is printed instead.
set -eo pipefail   # deliberately not -u

TAG=${1:?tag, e.g. v1.0.0}; STAGE=${2:?stage dir}; shift 2
DRY=0; PRE=""
for a in "$@"; do case "$a" in --dry-run) DRY=1;; --prerelease) PRE="--prerelease";; *) echo "unknown arg $a" >&2; exit 2;; esac; done
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO_DIR"

echo "== 1. tag ↔ commit"
HEAD=$(git rev-parse HEAD)
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  TAGGED=$(git rev-parse "$TAG^{commit}")
  [ "$TAGGED" = "$HEAD" ] || { echo "tag $TAG points at $TAGGED but HEAD is $HEAD — refusing"; exit 3; }
  echo "   tag exists and matches HEAD $HEAD"
else
  echo "   tag $TAG does not exist yet; it will be created at HEAD $HEAD"
fi
[ -z "$(git status --porcelain)" ] || { echo "   working tree not clean — commit or stash first"; git status --porcelain | head; exit 3; }

echo "== 2. stage integrity"
for f in SHA256SUMS RELEASE-NOTES.md THIRD-PARTY-NOTICES.md; do [ -s "$STAGE/$f" ] || { echo "   missing $STAGE/$f"; exit 4; }; done
( cd "$STAGE" && sha256sum -c --quiet SHA256SUMS ); rc=$?; [ $rc -eq 0 ] || { echo "   SHA256SUMS verification failed rc=$rc"; exit 4; }
echo "   $(wc -l < "$STAGE/SHA256SUMS") sums verified"

echo "== 3. ship gate"
python3 -I tools/ship-gate.py --stage "$STAGE" --repo . --json "$STAGE/SHIP-GATE-REPORT.json"; rc=$?
[ $rc -eq 0 ] || { echo "   SHIP GATE FAILED rc=$rc — nothing is published"; exit 5; }

echo "== 4. assets"
VER=${TAG#v}
ASSETS=()
while IFS= read -r f; do
  rel=${f#"$STAGE"/}; unit=${rel%%/*}; rest=${rel#*/}; arch=${rest%%/*}; base=$(basename "$f")
  case "$base" in SHA256SUMS|RELEASE-NOTES.md|THIRD-PARTY-NOTICES.md|SHIP-GATE-REPORT.json|BUILD-RECORD.md|cargo-metadata.json) continue;; esac
  [ "$arch" = "$rest" ] && arch="noarch"
  case "$arch" in noarch|x86_64|aarch64|armv7|i686) ;; *) echo "   $rel: unknown arch dir '$arch' — stage layout is <unit>/<arch>/<file>"; exit 6;; esac
  name=$base
  if ! printf '%s' "$name" | grep -q -E -- "-(noarch|linux-(x86_64|aarch64|armv7|i686))[.-]"; then
    ext=${name#*.}; stem=${name%%.*}
    if [ "$arch" = noarch ]; then name="${stem}-noarch.${ext}"; else name="${stem}-linux-${arch}.${ext}"; fi
  fi
  ASSETS+=("$f#$name")
done < <(find "$STAGE" -mindepth 2 -type f | sort)
for extra in SHA256SUMS THIRD-PARTY-NOTICES.md SHIP-GATE-REPORT.json; do ASSETS+=("$STAGE/$extra#$extra"); done
printf '   %s\n' "${ASSETS[@]#*#}"

echo "== 5. publish"
if gh release view "$TAG" >/dev/null 2>&1; then echo "   release $TAG already exists — releases are immutable; bump the tag"; exit 7; fi
CMD=(gh release create "$TAG" --title "SyMoNsAyLeaRn $TAG" --notes-file "$STAGE/RELEASE-NOTES.md" --target "$HEAD" $PRE "${ASSETS[@]}")
if [ $DRY -eq 1 ]; then echo "   DRY RUN — would run:"; printf '   %q ' "${CMD[@]}"; echo; exit 0; fi
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { git tag -a "$TAG" -m "SyMoNsAyLeaRn $TAG"; git push origin "refs/tags/$TAG"; echo "   tag pushed"; }
"${CMD[@]}"; rc=$?
[ $rc -eq 0 ] || { echo "   gh release create rc=$rc"; exit 8; }
gh release view "$TAG" --json tagName,isLatest,assets --jq '{tag:.tagName, latest:.isLatest, assets:[.assets[].name]}'
