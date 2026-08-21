#!/usr/bin/env bash
# Idempotent setup for the sdcopy tooling.
# sdcopy is a set of Bash scripts that sync an SD card / block device to a
# destination using rsync, notify via msmtp, and run headless under systemd+udev.
# This installs the runtime tools the scripts invoke plus shellcheck for linting.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

sudo -E apt-get update -qq
sudo -E apt-get install -y --no-install-recommends \
  rsync \
  msmtp \
  msmtp-mta \
  shellcheck

echo "sdcopy environment ready:"
rsync --version | head -1
msmtp --version | head -1
shellcheck --version | grep -i version | head -1
