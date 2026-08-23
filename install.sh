#!/usr/bin/env bash
set -euo pipefail

main() {
  local repository="${MOOLIAS_REPOSITORY:-vain90/Moolias}"
  local raw_base="https://raw.githubusercontent.com/${repository}"
  local latest_url="https://github.com/${repository}/releases/latest"
  local requested_ref="${MOOLIAS_INSTALL_REF:-}"
  local install_ref=""
  local latest_ref=""
  local final_url=""
  local tmp_file=""

  command -v curl >/dev/null 2>&1 || {
    echo "Moolias installer: required command not found: curl" >&2
    exit 1
  }

  if [[ -n "$requested_ref" ]]; then
    install_ref="$requested_ref"
  else
    final_url="$(
      curl --proto '=https' --tlsv1.2 -fsSL \
        -o /dev/null \
        -w '%{url_effective}' \
        "$latest_url"
    )" || {
      echo "Moolias installer: could not determine the latest stable release." >&2
      exit 1
    }

    latest_ref="${final_url##*/}"
    if [[ ! "$latest_ref" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([+][0-9A-Za-z.-]+)?$ ]]; then
      echo "Moolias installer: unexpected latest release tag: ${latest_ref}" >&2
      exit 1
    fi

    if curl --proto '=https' --tlsv1.2 -fsSL \
      -o /dev/null \
      "${raw_base}/${latest_ref}/compose.mailcow.yml" \
      && curl --proto '=https' --tlsv1.2 -fsSL \
        -o /dev/null \
        "${raw_base}/${latest_ref}/scripts/install.sh"; then
      install_ref="$latest_ref"
    else
      install_ref="main"
      printf '%s\n' \
        "The latest stable release predates the Mailcow-host installer." \
        "Using installer files from main; the Moolias application image remains on the stable latest channel."
    fi
  fi

  if [[ ! "$install_ref" =~ ^[A-Za-z0-9._/+:-]+$ ]]; then
    echo "Moolias installer: MOOLIAS_INSTALL_REF contains unsupported characters." >&2
    exit 1
  fi

  tmp_file="$(mktemp)"
  trap 'rm -f "$tmp_file"' EXIT

  curl --proto '=https' --tlsv1.2 -fsSL \
    "${raw_base}/${install_ref}/scripts/install.sh" \
    -o "$tmp_file" \
    || {
      echo "Moolias installer: could not download installer from ${install_ref}." >&2
      exit 1
    }

  bash -n "$tmp_file" || {
    echo "Moolias installer: downloaded installer failed syntax validation." >&2
    exit 1
  }

  MOOLIAS_INSTALL_REF="$install_ref" bash "$tmp_file" "$@"
}

main "$@"
