#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEST_ROOT=${TEST_ROOT:-$(mktemp -d)}
rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
trap 'rm -rf "$TEST_ROOT"' EXIT

export GNUPGHOME="$TEST_ROOT/gnupg"
mkdir -m 0700 "$GNUPGHOME"
gpg --batch --passphrase '' --quick-generate-key "KubeBot repository test" rsa2048 sign 1d
export PACKAGE_SIGNING_KEY_ID="KubeBot repository test"
export OUTPUT_DIR="$TEST_ROOT/repository"

"$ROOT/scripts/build-package-repositories.sh"

gpg --verify "$OUTPUT_DIR/apt/dists/stable/Release.gpg" "$OUTPUT_DIR/apt/dists/stable/Release"
gpg --verify "$OUTPUT_DIR/rpm/x86_64/repodata/repomd.xml.asc" "$OUTPUT_DIR/rpm/x86_64/repodata/repomd.xml"
gpg --verify "$OUTPUT_DIR/arch/x86_64/kubebot.db.tar.gz.sig" "$OUTPUT_DIR/arch/x86_64/kubebot.db.tar.gz"
ARCH_PACKAGE=$(find "$OUTPUT_DIR/arch/x86_64" -maxdepth 1 -name '*.pkg.tar.zst' -print -quit)
gpg --verify "$ARCH_PACKAGE.sig" "$ARCH_PACKAGE"
RPM_PACKAGE=$(find "$OUTPUT_DIR/rpm/x86_64" -maxdepth 1 -name '*.rpm' -print -quit)
rpm --import "$OUTPUT_DIR/kubebot-archive-key.asc"
rpm --checksig "$RPM_PACKAGE"
test -s "$OUTPUT_DIR/apt/dists/stable/main/binary-amd64/Packages.gz"
test -s "$OUTPUT_DIR/rpm/x86_64/repodata/repomd.xml"
test -L "$OUTPUT_DIR/arch/x86_64/kubebot.db"
grep -q '^gpgcheck=1$' "$OUTPUT_DIR/kubebot.repo"
grep -q '^repo_gpgcheck=1$' "$OUTPUT_DIR/kubebot.repo"