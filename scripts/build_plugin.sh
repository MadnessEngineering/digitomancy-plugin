#!/usr/bin/env bash
# Assemble the Claude plugin: plugin/ + a copy of the Python package as server/.
# Output: dist/digitomancy/ (unpacked) and dist/digitomancy.plugin (zip).
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
echo "built $out and dist/digitomancy.plugin"
