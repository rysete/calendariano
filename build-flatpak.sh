#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BUILD_DIR="$ROOT_DIR/.flatpak-build"
REPO_DIR="$ROOT_DIR/.flatpak-repo"
MANIFEST="$ROOT_DIR/flatpak/org.ryse.EscalaWebEditor.yml"

flatpak-builder --force-clean --user --install --repo="$REPO_DIR" "$BUILD_DIR" "$MANIFEST"

echo
echo "Instalado. Rode com:"
echo "  flatpak run org.ryse.EscalaWebEditor"
