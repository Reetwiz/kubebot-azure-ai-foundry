#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEB=$(find "$ROOT/dist/packages" -maxdepth 1 -name '*.deb' -print -quit)
RPM=$(find "$ROOT/dist/packages" -maxdepth 1 -name '*.rpm' -print -quit)
ARCH=$(find "$ROOT/dist/packages" -maxdepth 1 -name '*.pkg.tar.zst' -print -quit)

test -n "$DEB" && test -n "$RPM" && test -n "$ARCH"

docker run --rm -v "$DEB:/tmp/kubebot.deb:ro" ubuntu:24.04 sh -c \
    'apt-get update >/dev/null && apt-get install -y /tmp/kubebot.deb >/dev/null && \
     kubebot --version && mkdir /tmp/untrusted && \
     printf "KUBEBOT_LLM_PROVIDER=invalid\n" > /tmp/untrusted/.env && \
     cd /tmp/untrusted && printf "ollama\n" | HOME=/tmp/kubebot-home kubebot --configure && \
     grep -q "KUBEBOT_LLM_PROVIDER=ollama" /tmp/kubebot-home/.config/kubebot/.env && \
     test "$(stat -c %a /tmp/kubebot-home/.config/kubebot/.env)" = 600'
docker run --rm -v "$RPM:/tmp/kubebot.rpm:ro" fedora:42 sh -c \
    'dnf install -y /tmp/kubebot.rpm >/dev/null && kubebot --version'
docker run --rm -v "$ARCH:/tmp/kubebot.pkg.tar.zst:ro" archlinux:base sh -c \
    'pacman -Sy --noconfirm >/dev/null && pacman -U --noconfirm /tmp/kubebot.pkg.tar.zst >/dev/null && kubebot --version'