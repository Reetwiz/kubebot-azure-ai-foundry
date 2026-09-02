#!/usr/bin/env sh
set -eu

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required: https://brew.sh" >&2
    exit 1
fi

brew install python pipx kubectl
pipx ensurepath
pipx install --force "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

echo "KubeBot installed. Open a new terminal and run: kubebot"