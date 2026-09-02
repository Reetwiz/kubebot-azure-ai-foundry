#!/usr/bin/env sh
set -eu

. /etc/os-release

case "${ID_LIKE:-$ID}" in
    *debian*|*ubuntu*)
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv pipx
        ;;
    *fedora*|*rhel*|*centos*)
        sudo dnf install -y python3 python3-pip pipx
        ;;
    *arch*)
        sudo pacman -Syu --needed python python-pip python-pipx kubectl
        ;;
    *suse*)
        sudo zypper --non-interactive install python3 python3-pip python3-virtualenv
        python3 -m pip install --user pipx
        ;;
    *)
        echo "Unsupported distribution: ${PRETTY_NAME:-$ID}" >&2
        echo "Install Python 3.10+, pipx, and kubectl, then run: pipx install ." >&2
        exit 1
        ;;
esac

python3 -m pipx ensurepath
python3 -m pipx install --force "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl was not found. Install it from https://kubernetes.io/docs/tasks/tools/"
fi

echo "KubeBot installed. Open a new terminal and run: kubebot"