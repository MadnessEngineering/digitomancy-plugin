#!/usr/bin/env bash
# Assemble the Claude plugin: plugin/ + a copy of the Python package as server/.
# Output: dist/digitomancy/ (unpacked), dist/digitomancy.plugin (zip), and
# dist/.claude-plugin/marketplace.json so dist/ is a local marketplace:
#   claude plugin marketplace add ./dist && claude plugin install digitomancy@digitomancy-local
set -euo pipefail
cd "$(dirname "$0")/.."

out=dist/digitomancy
rm -rf "$out" dist/digitomancy.plugin
mkdir -p "$out/server"
cp -R plugin/. "$out/"
cp LICENSE "$out/"
cp pyproject.toml uv.lock README.md LICENSE "$out/server/"
rsync -a --exclude '__pycache__' src "$out/server/"

(cd "$out" && zip -qr ../digitomancy.plugin . -x '*.DS_Store')

version=$(python3 -c 'import json; print(json.load(open("plugin/.claude-plugin/plugin.json"))["version"])')
mkdir -p dist/.claude-plugin
cat > dist/.claude-plugin/marketplace.json <<JSON
{
  "name": "digitomancy-local",
  "owner": {"name": "Madness Engineering"},
  "description": "Local build of the Digitomancy Android automation plugin.",
  "plugins": [
    {
      "name": "digitomancy",
      "source": "./digitomancy",
      "version": "$version",
      "description": "Drive an Android phone or emulator from Claude: anchors, checkpoints, resumable routines, Tasker bridge."
    }
  ]
}
JSON
echo "built $out and dist/digitomancy.plugin"
