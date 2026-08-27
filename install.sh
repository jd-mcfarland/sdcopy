#!/usr/bin/env bash
set -euo pipefail

# Install sdcopy units, udev rules, and a Python venv.
# Usage: sudo ./install.sh
# Optional env: SDCOPY_USER SDCOPY_GROUP PREFIX STATE_DIR ETC_DIR

if [[ ${EUID} -ne 0 ]]; then
  echo "install.sh must run as root so it can install udev and systemd units." >&2
  exit 1
fi

USER_NAME=${SDCOPY_USER:-nas}
GROUP_NAME=${SDCOPY_GROUP:-sdcopy}
PREFIX=${PREFIX:-/usr/local/lib/sdcopy}
STATE_DIR=${STATE_DIR:-/var/lib/sdcopy}
ETC_DIR=${ETC_DIR:-/etc/sdcopy}
REPO_DIR=$(cd "$(dirname "$0")" && pwd)
VENV=${PREFIX}/venv

if ! id -u "${USER_NAME}" >/dev/null 2>&1; then
  echo "User ${USER_NAME} does not exist. Create it or set SDCOPY_USER." >&2
  exit 1
fi

if ! getent group "${GROUP_NAME}" >/dev/null; then
  groupadd --system "${GROUP_NAME}"
fi
usermod -a -G "${GROUP_NAME}" "${USER_NAME}" || true

mkdir -p "${PREFIX}" "${STATE_DIR}/jobs" "${ETC_DIR}" /var/log/sdcopy /etc/udev/rules.d /etc/systemd/system
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install "${REPO_DIR}"

install -m 0644 "${REPO_DIR}/udev/99-sdcopy.rules" /etc/udev/rules.d/99-sdcopy.rules

replace() {
  sed \
    -e "s|@@USER@@|${USER_NAME}|g" \
    -e "s|@@GROUP@@|${GROUP_NAME}|g" \
    -e "s|@@VENV@@|${VENV}|g" \
    -e "s|@@STATE@@|${STATE_DIR}|g" \
    -e "s|@@ETC@@|${ETC_DIR}|g"
}

replace < "${REPO_DIR}/systemd/sdcopy@.service" > /etc/systemd/system/sdcopy@.service
replace < "${REPO_DIR}/systemd/sdcopy-web.service" > /etc/systemd/system/sdcopy-web.service
chmod 0644 /etc/systemd/system/sdcopy@.service /etc/systemd/system/sdcopy-web.service

if [[ ! -f "${ETC_DIR}/config.json" ]]; then
  sed -e "s|\"nas\"|\"${USER_NAME}\"|g" -e "s|\"sdcopy\"|\"${GROUP_NAME}\"|g" \
    "${REPO_DIR}/sdcopy.conf.example" > "${ETC_DIR}/config.json"
fi

chown -R "${USER_NAME}:${GROUP_NAME}" "${STATE_DIR}"
chown "${USER_NAME}:${GROUP_NAME}" /var/log/sdcopy
chmod 0750 "${STATE_DIR}"

udevadm control --reload-rules || true
systemctl daemon-reload
systemctl enable --now sdcopy-web.service

echo
echo "sdcopy installed."
echo "UI: http://127.0.0.1:8743"
echo "Onboard the first card in the UI or: ${VENV}/bin/sdcopy onboard UUID --nickname 'Camera card'"
echo "Do not enable sdcopy@.service at boot; udev starts it per device."
