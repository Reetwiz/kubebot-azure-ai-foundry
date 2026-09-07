#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PACKAGES_DIR=${PACKAGES_DIR:-$ROOT/dist/packages}
OUTPUT_DIR=${OUTPUT_DIR:-$ROOT/dist/repository}
CODENAME=${CODENAME:-stable}

DEB=$(find "$PACKAGES_DIR" -maxdepth 1 -name '*.deb' -print -quit)
RPM=$(find "$PACKAGES_DIR" -maxdepth 1 -name '*.rpm' -print -quit)
ARCH=$(find "$PACKAGES_DIR" -maxdepth 1 -name '*.pkg.tar.zst' -print -quit)
test -n "$DEB" && test -n "$RPM" && test -n "$ARCH"
command -v dpkg-scanpackages >/dev/null
command -v apt-ftparchive >/dev/null
command -v createrepo_c >/dev/null
command -v gpg >/dev/null
command -v rpmsign >/dev/null

rm -rf "$OUTPUT_DIR"
mkdir -p \
    "$OUTPUT_DIR/apt/pool/main/k/kubebot" \
    "$OUTPUT_DIR/apt/dists/$CODENAME/main/binary-amd64" \
    "$OUTPUT_DIR/rpm/x86_64" \
    "$OUTPUT_DIR/arch/x86_64"

cp "$DEB" "$OUTPUT_DIR/apt/pool/main/k/kubebot/"
cp "$RPM" "$OUTPUT_DIR/rpm/x86_64/"
cp "$ARCH" "$OUTPUT_DIR/arch/x86_64/"

RPM_COPY=$(find "$OUTPUT_DIR/rpm/x86_64" -maxdepth 1 -name '*.rpm' -print -quit)
ARCH_COPY=$(find "$OUTPUT_DIR/arch/x86_64" -maxdepth 1 -name '*.pkg.tar.zst' -print -quit)
rpmsign --addsign \
    --define "_gpg_name $PACKAGE_SIGNING_KEY_ID" \
    --define "__gpg /usr/bin/gpg" \
    "$RPM_COPY"
gpg --batch --yes --local-user "$PACKAGE_SIGNING_KEY_ID" --detach-sign "$ARCH_COPY"

(
    cd "$OUTPUT_DIR/apt"
    dpkg-scanpackages --multiversion pool /dev/null > "dists/$CODENAME/main/binary-amd64/Packages"
    gzip -9nk "dists/$CODENAME/main/binary-amd64/Packages"
    apt-ftparchive \
        -o APT::FTPArchive::Release::Origin=KubeBot \
        -o APT::FTPArchive::Release::Label=KubeBot \
        -o APT::FTPArchive::Release::Suite="$CODENAME" \
        -o APT::FTPArchive::Release::Codename="$CODENAME" \
        -o APT::FTPArchive::Release::Architectures=amd64 \
        -o APT::FTPArchive::Release::Components=main \
        release "dists/$CODENAME" > "dists/$CODENAME/Release"
)

createrepo_c "$OUTPUT_DIR/rpm/x86_64"
if command -v docker >/dev/null 2>&1; then
    docker run --rm \
        -v "$OUTPUT_DIR/arch/x86_64:/repository" \
        -w /repository \
        archlinux:base sh -c \
        'pacman -Sy --noconfirm pacman-contrib >/dev/null && repo-add kubebot.db.tar.gz ./*.pkg.tar.zst'
elif command -v repo-add >/dev/null 2>&1; then
    (
        cd "$OUTPUT_DIR/arch/x86_64"
        repo-add kubebot.db.tar.gz ./*.pkg.tar.zst
    )
else
    echo "Install Docker or Arch repo-add to generate repository metadata." >&2
    exit 1
fi
ln -sf kubebot.db.tar.gz "$OUTPUT_DIR/arch/x86_64/kubebot.db"
ln -sf kubebot.files.tar.gz "$OUTPUT_DIR/arch/x86_64/kubebot.files"

gpg --batch --yes --armor --export "$PACKAGE_SIGNING_KEY_ID" > "$OUTPUT_DIR/kubebot-archive-key.asc"
gpg --batch --yes --local-user "$PACKAGE_SIGNING_KEY_ID" --clearsign \
    --output "$OUTPUT_DIR/apt/dists/$CODENAME/InRelease" \
    "$OUTPUT_DIR/apt/dists/$CODENAME/Release"
gpg --batch --yes --local-user "$PACKAGE_SIGNING_KEY_ID" --detach-sign --armor \
    --output "$OUTPUT_DIR/apt/dists/$CODENAME/Release.gpg" \
    "$OUTPUT_DIR/apt/dists/$CODENAME/Release"
gpg --batch --yes --local-user "$PACKAGE_SIGNING_KEY_ID" --detach-sign --armor "$OUTPUT_DIR/rpm/x86_64/repodata/repomd.xml"
gpg --batch --yes --local-user "$PACKAGE_SIGNING_KEY_ID" --detach-sign "$OUTPUT_DIR/arch/x86_64/kubebot.db.tar.gz"

cat > "$OUTPUT_DIR/kubebot.repo" <<EOF
[kubebot]
name=KubeBot
baseurl=https://reetwiz.github.io/kubebot-azure-ai-foundry/rpm/x86_64
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://reetwiz.github.io/kubebot-azure-ai-foundry/kubebot-archive-key.asc
EOF

touch "$OUTPUT_DIR/.nojekyll"