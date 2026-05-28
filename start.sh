#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo
echo " ==========================================="
echo "        NETWORK MAP - Live Monitor"
echo " ==========================================="
echo

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  fi
fi

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

detect_pkg_manager() {
  if have_cmd apt-get; then echo "apt"; return; fi
  if have_cmd dnf; then echo "dnf"; return; fi
  if have_cmd yum; then echo "yum"; return; fi
  if have_cmd pacman; then echo "pacman"; return; fi
  if have_cmd zypper; then echo "zypper"; return; fi
  if have_cmd apk; then echo "apk"; return; fi
  echo ""
}

install_packages() {
  if [ "$#" -eq 0 ]; then
    return 0
  fi

  local pm
  pm="$(detect_pkg_manager)"
  if [ -z "$pm" ]; then
    echo " No supported package manager found. Please install manually: $*"
    return 1
  fi

  if [ -z "$SUDO" ] && [ "$(id -u)" -ne 0 ]; then
    echo " sudo is not available. Please install manually: $*"
    return 1
  fi

  echo " Installing missing system packages: $*"
  case "$pm" in
    apt)
      $SUDO apt-get update
      $SUDO apt-get install -y "$@"
      ;;
    dnf)
      $SUDO dnf install -y "$@"
      ;;
    yum)
      $SUDO yum install -y "$@"
      ;;
    pacman)
      $SUDO pacman -Sy --needed --noconfirm "$@"
      ;;
    zypper)
      $SUDO zypper --non-interactive install "$@"
      ;;
    apk)
      $SUDO apk add --no-cache "$@"
      ;;
  esac
}

ensure_system_dependencies() {
  local pm missing=()
  pm="$(detect_pkg_manager)"

  if ! have_cmd python3; then
    case "$pm" in
      apt) missing+=(python3 python3-venv python3-pip) ;;
      dnf|yum|zypper) missing+=(python3 python3-pip) ;;
      pacman) missing+=(python python-pip) ;;
      apk) missing+=(python3 py3-pip) ;;
      *) missing+=(python3) ;;
    esac
  fi

  if have_cmd python3 && ! python3 -m venv --help >/dev/null 2>&1; then
    case "$pm" in
      apt) missing+=(python3-venv) ;;
    esac
  fi

  if ! have_cmd traceroute; then
    missing+=(traceroute)
  fi

  if [ "${#missing[@]}" -gt 0 ]; then
    install_packages "${missing[@]}"
  fi
}

ensure_python_version() {
  if ! have_cmd python3; then
    echo " python3 was not found and could not be installed automatically."
    exit 1
  fi

  python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9 or newer is required.")
PY
}

ensure_system_dependencies
ensure_python_version

if [ ! -x ".venv/bin/python" ]; then
  echo " [1/3] Creating virtual environment..."
  python3 -m venv .venv
fi

echo " [2/3] Installing Python dependencies..."
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt

echo
echo " [3/3] Starting server..."
echo " Open http://localhost:5000 in your browser"
echo
exec ".venv/bin/python" app.py
