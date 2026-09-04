#!/usr/bin/env sh
set -eu

VERSION=${VERSION:-$(python3 -c 'from kubebot import __version__; print(__version__)')}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

cd "$ROOT"
rm -rf dist/package-root dist/packages
mkdir -p dist/package-root/usr/lib/kubebot/runtime dist/packages

if ! command -v uv >/dev/null 2>&1; then
    echo "Install uv to build the bundled Python runtime." >&2
    exit 1
fi

uv python install 3.12 \
    --install-dir dist/package-root/usr/lib/kubebot/runtime \
    --no-bin
RUNTIME_PYTHON=$(find dist/package-root/usr/lib/kubebot/runtime -path '*/bin/python3.12' -type f -print -quit)
test -n "$RUNTIME_PYTHON"
uv pip install --python "$RUNTIME_PYTHON" --break-system-packages --no-compile .

for format in deb rpm archlinux; do
    if command -v nfpm >/dev/null 2>&1; then
        VERSION="$VERSION" nfpm package \
            --config packaging/nfpm.yaml \
            --packager "$format" \
            --target dist/packages/
    elif command -v docker >/dev/null 2>&1; then
        docker run --rm \
            -e VERSION="$VERSION" \
            -v "$ROOT:/workspace" \
            -w /workspace \
            ghcr.io/goreleaser/nfpm:v2.43.4 package \
            --config packaging/nfpm.yaml \
            --packager "$format" \
            --target dist/packages/
    else
        echo "Install nfpm or Docker to build native packages." >&2
        exit 1
    fi
done