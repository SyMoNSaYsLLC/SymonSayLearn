#!/bin/bash
# Install the tracked SyMoNeuRaL configuration into the Claude Desktop 3p profile.
#
# WHY THIS REFUSES TO RUN WHILE THE APP IS OPEN
# ---------------------------------------------
# The app owns ~/.config/Claude-3p/configLibrary/ and rewrites both the entry file
# and _meta.json when it saves. Editing those files under a live app means the app's
# in-memory copy wins on its next write and this change vanishes with no error
# anywhere. Quit the app first.
#
# WHAT THIS DOES NOT DO
# ---------------------
# It never writes a credential. inferenceGatewayApiKey is absent from the tracked
# JSON on purpose and stays in the app window plus ~/.config/symoneural/gateway-9001.key
# (0600). If an existing entry already holds a credential, it is carried across
# untouched and never printed.
set -u

SRC=$(dirname -- "${BASH_SOURCE[0]}")/symonAI.json
PROFILE=${CLAUDE_3P_DIR:-$HOME/.config/Claude-3p}
LIB=$PROFILE/configLibrary
ID=symonAI
STAMP=$(date +%Y%m%d-%H%M%S)

die() { echo "ERROR: $*" >&2; exit 1; }

[ -r "$SRC" ] || die "missing $SRC"
[ -d "$LIB" ] || die "no config library at $LIB (is Claude Desktop installed and has it run once?)"

if pgrep -x claude-desktop >/dev/null; then
  die "Claude Desktop is running. Quit it completely, then re-run. See the header for why."
fi

BAK=$LIB.bak-$STAMP
cp -a "$LIB" "$BAK" || die "backup failed"
echo "backup: $BAK"

python3 - "$SRC" "$LIB" "$ID" <<'PY'
import json, os, sys, glob

src, lib, new_id = sys.argv[1], sys.argv[2], sys.argv[3]
desired = {k: v for k, v in json.load(open(src)).items() if not k.startswith("_")}

meta_path = os.path.join(lib, "_meta.json")
meta = {"appliedId": None, "entries": []}
if os.path.exists(meta_path):
    try:
        meta = json.load(open(meta_path))
    except json.JSONDecodeError:
        print("_meta.json was unreadable; rebuilding it")

# Carry a credential across if a previous entry held one. It is moved, never shown:
# the value is read and rewritten without being printed or logged.
carried = None
for old in glob.glob(os.path.join(lib, "*.json")):
    if os.path.basename(old) == "_meta.json":
        continue
    try:
        blob = json.load(open(old))
    except (json.JSONDecodeError, OSError):
        continue
    if isinstance(blob, dict) and blob.get("inferenceGatewayApiKey"):
        carried = blob["inferenceGatewayApiKey"]
if carried:
    desired["inferenceGatewayApiKey"] = carried
    print("carried an existing credential across (value not shown)")
else:
    print("no existing credential found; paste the key in the app window after applying")

dest = os.path.join(lib, f"{new_id}.json")
fd = os.open(dest, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as fh:
    json.dump(desired, fh, indent=2)
print("wrote", dest)

entries = [e for e in meta.get("entries", []) if e.get("id") != new_id]
entries.insert(0, {"id": new_id, "name": "SyMoNeuRaL"})
meta["entries"] = entries
meta["appliedId"] = new_id
fd = os.open(meta_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as fh:
    json.dump(meta, fh, indent=2)
print("applied id:", new_id)

# Report the keys installed, so the operator can see what changed without opening
# the file. Any credential-shaped key is named but never valued.
for k in sorted(desired):
    print("  ", k, "=", "<withheld>" if "apikey" in k.lower() or "token" in k.lower() else desired[k])
PY
rc=$?
[ $rc -eq 0 ] || die "install failed (rc=$rc); the backup at $BAK is untouched"

echo
echo "Installed. Now:"
echo "  1. Start Claude Desktop."
echo "  2. Developer > Configure Third-Party Inference: confirm the SyMoNeuRaL entry is applied."
echo "  3. Paste the gateway key if the field is empty."
echo "  4. Press Test. Apply only after Test passes."
echo
echo "Revert:  rm -rf '$LIB' && mv '$BAK' '$LIB'"
