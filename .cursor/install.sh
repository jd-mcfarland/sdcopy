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
# Report versions without piping into `head` so an early pipe close cannot
# raise SIGPIPE (exit 141) under `set -o pipefail`.
echo "  rsync:      $(rsync --version | sed -n '1p')"
echo "  msmtp:      $(msmtp --version | sed -n '1p')"
echo "  shellcheck: $(shellcheck --version | sed -n '2p')"
