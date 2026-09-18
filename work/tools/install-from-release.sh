#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
#
# install-from-release — install SyMoNsAyLeaRn units from a GitHub release, verified first.
#
#   tools/install-from-release.sh                              # latest release, all units for this machine
#   tools/install-from-release.sh --release v1.0.0             # a given release
#   tools/install-from-release.sh --units gateway,image        # a subset
#   tools/install-from-release.sh --dstdir ~/.local/bin --home ~/.local/share/symoneural-learn
#   tools/install-from-release.sh --dry-run                    # show what would happen
#
# What it does, in order:
#   1. detects the machine architecture and maps it to the release's arch names
#      (x86_64, aarch64, armv7, i686); noarch units install everywhere
#   2. downloads SHA256SUMS and the assets for the chosen units into a temp dir
#      (through `gh` when it is authenticated — the repository is private — or through
#      curl with GITHUB_TOKEN)
#   3. verifies every downloaded asset against SHA256SUMS. Nothing is installed if one fails.
#   4. installs: wheels into a virtual environment under --home, with their console scripts
#      linked into --dstdir; binary units under --home/<unit>/ with a launcher linked into
#      --dstdir; tarballs of scripts under --home/<unit>/
#   5. prints what was installed, with the hash of each asset
# Nothing here needs root unless --dstdir is not writable by you; then it uses sudo for the
# link step only.
set -o pipefail

REPO=${SYM_RELEASE_REPO:-SyMoNSaYsLLC/symoneural-learn}
release=latest; dstdir=/usr/local/bin; home=${SYM_HOME:-$HOME/.local/share/symoneural-learn}
units=""; dry=0; tmpdir=${TMPDIR:-/tmp}
usage() { sed -n '6,26p' "$0" | sed 's/^# \{0,1\}//'; }
while (( $# )); do
  case "$1" in
    -h|--help) usage; exit 0;;
    --release) release=$2; shift 2;;
    --dstdir) dstdir=$2; shift 2;;
    --home) home=$2; shift 2;;
    --units) units=$2; shift 2;;
    --tmpdir) tmpdir=$2; shift 2;;
    --dry-run) dry=1; shift;;
    *) echo "unknown argument: $1" >&2; usage; exit 2;;
  esac
done

case "$(uname -m)" in
  x86_64) arch=x86_64;; aarch64|arm64) arch=aarch64;; armv7l|armv7) arch=armv7;; i686|i386) arch=i686;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 3;;
esac
echo "machine: linux/$arch   release: $release   home: $home   dstdir: $dstdir"

# The unit table: name | kind | asset pattern (the release's naming: <unit>-<ver>-noarch.<ext> or -linux-<arch>.<ext>) | launcher
UNITS="gateway|wheel|symoneural_gateway-*-py3-none-any.whl|symoneural-gateway
api|wheel|symoneural_api-*-py3-none-any.whl|symoneural-api
llm|wheel|symoneural_llm-*-py3-none-any.whl|symoneural-llm
hostrun|tar|symoneural-learn-hostrun-*.tar.gz|
image|binary|symoneural-image-cuda-*-linux-${arch}.tar.gz|symoneural-image
api-native|binary|symoneural-api-native-*-linux-${arch}.tar.gz|"
[ -n "$units" ] || units=$(echo "$UNITS" | cut -d'|' -f1 | tr '\n' ',' | sed 's/,$//')

# ---- fetch --------------------------------------------------------------------------------
work=$(mktemp -d -t symoneural-install-XXXXXX --tmpdir="$tmpdir") || exit 4
trap 'rm -rf "$work"' EXIT
fetch() { # pattern -> downloads matching assets into $work
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    if [ "$release" = latest ]; then gh release download -R "$REPO" -p "$1" -D "$work" --clobber; else gh release download "$release" -R "$REPO" -p "$1" -D "$work" --clobber; fi; return $?
  fi
  [ -n "$GITHUB_TOKEN" ] || { echo "the repository is private: authenticate gh, or export GITHUB_TOKEN" >&2; return 5; }
  local api; if [ "$release" = latest ]; then api="https://api.github.com/repos/$REPO/releases/latest"; else api="https://api.github.com/repos/$REPO/releases/tags/$release"; fi
  curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" "$api" \
    | python3 -c 'import sys,json,fnmatch; pat=sys.argv[1]; [print(a["id"], a["name"]) for a in json.load(sys.stdin)["assets"] if fnmatch.fnmatch(a["name"], pat)]' "$1" \
    | while read -r id name; do curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/octet-stream" -o "$work/$name" "https://api.github.com/repos/$REPO/releases/assets/$id" || return 6; done
}
if [ $dry -eq 1 ]; then echo "DRY RUN — would fetch from $REPO:"; echo "  SHA256SUMS"; for u in ${units//,/ }; do echo "  $(echo "$UNITS" | awk -F'|' -v u="$u" '$1==u{print $3}')"; done; exit 0; fi
fetch SHA256SUMS; rc=$?; [ $rc -eq 0 ] && [ -s "$work/SHA256SUMS" ] || { echo "could not fetch SHA256SUMS (rc=$rc) — refusing to install anything unverified" >&2; exit 7; }
for u in ${units//,/ }; do pat=$(echo "$UNITS" | awk -F'|' -v u="$u" '$1==u{print $3}'); [ -n "$pat" ] || { echo "unknown unit: $u" >&2; exit 2; }; fetch "$pat"; rc=$?; [ $rc -eq 0 ] || { echo "fetch failed for $u (rc=$rc)" >&2; exit 7; }; done

# ---- verify: every downloaded asset must appear in SHA256SUMS and match --------------------
echo "verifying:"; fail=0
for f in "$work"/*; do n=$(basename "$f"); [ "$n" = SHA256SUMS ] && continue
  want=$(awk -v n="$n" '{sub(/^\.\//,"",$2); if ($2 ~ ("(^|/)" n "$")) print $1}' "$work/SHA256SUMS" | head -1)
  have=$(sha256sum "$f" | cut -c1-64)
  if [ -z "$want" ]; then echo "  MISSING from SHA256SUMS: $n"; fail=1; elif [ "$want" != "$have" ]; then echo "  MISMATCH: $n"; fail=1; else echo "  ok  ${have:0:16}  $n"; fi
done
[ $fail -eq 0 ] || { echo "verification failed — nothing installed" >&2; exit 8; }

# ---- install -----------------------------------------------------------------------------
SUDO=""; [ -w "$dstdir" ] || { mkdir -p "$dstdir" 2>/dev/null || SUDO=sudo; [ -w "$dstdir" ] || SUDO=sudo; }
mkdir -p "$home" || exit 9
link() { $SUDO ln -sfn "$1" "$dstdir/$2" && echo "  $dstdir/$2 -> $1"; }
for u in ${units//,/ }; do
  kind=$(echo "$UNITS" | awk -F'|' -v u="$u" '$1==u{print $2}'); pat=$(echo "$UNITS" | awk -F'|' -v u="$u" '$1==u{print $3}'); launcher=$(echo "$UNITS" | awk -F'|' -v u="$u" '$1==u{print $4}')
  set -- "$work"/$pat; asset=$1; [ -f "$asset" ] || { echo "no asset for $u on $arch (not built for this architecture)"; continue; }
  echo "installing $u:"
  case $kind in
    wheel) venv=$home/venv; [ -x "$venv/bin/python" ] || python3 -m venv "$venv" || exit 10
           "$venv/bin/pip" install -q --disable-pip-version-check --upgrade "$asset" || exit 10; [ -n "$launcher" ] && link "$venv/bin/$launcher" "$launcher";;
    tar)   mkdir -p "$home/$u" && tar -xzf "$asset" -C "$home/$u" --strip-components=1 && echo "  $home/$u/";;
    binary) mkdir -p "$home/$u" && tar -xzf "$asset" -C "$home/$u" && echo "  $home/$u/"; [ -n "$launcher" ] && [ -x "$home/$u/bin/$launcher" ] && link "$home/$u/bin/$launcher" "$launcher";;
  esac
done
echo "installed. Configuration: copy the release's symoneural-learn.env.example to ~/.config/symoneural/learn.env and source it before starting units."
