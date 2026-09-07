#!/usr/bin/env sh
set -eu

REPOSITORY=${KUBEBOT_GITHUB_REPOSITORY:-Reetwiz/kubebot-azure-ai-foundry}

if [ "${KUBEBOT_SKIP_SYSTEM_PACKAGES:-0}" != "1" ]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "Homebrew is required: https://brew.sh" >&2
        exit 1
    fi
    brew install python pipx kubectl
fi

python3 -m pip install --user pipx
python3 -m pipx ensurepath

if [ -n "${KUBEBOT_INSTALL_SOURCE:-}" ]; then
    INSTALL_SOURCE=$KUBEBOT_INSTALL_SOURCE
else
    INSTALL_SOURCE=$(python3 - "$REPOSITORY" <<'PY'
import json
import sys
import urllib.request

repository = sys.argv[1]
with urllib.request.urlopen(f"https://api.github.com/repos/{repository}/releases/latest") as response:
    release = json.load(response)
for asset in release["assets"]:
    if asset["name"].endswith("-py3-none-any.whl"):
        print(asset["browser_download_url"])
        break
else:
    raise SystemExit("The latest release has no Python wheel.")
PY
    )
fi

python3 -m pipx install --force "$INSTALL_SOURCE"

echo "KubeBot installed. Open a new terminal and run: kubebot"