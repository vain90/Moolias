#!/usr/bin/env bash
set -euo pipefail

main() {
  local repository="${MOOLIAS_REPOSITORY:-vain90/Moolias}"
  local raw_base="https://raw.githubusercontent.com/${repository}"
  local latest_url="https://github.com/${repository}/releases/latest"
  local requested_ref="${MOOLIAS_INSTALL_REF:-}"
  local source_dir="${MOOLIAS_SOURCE_DIR:-}"
  local install_ref=""
  local latest_ref=""
  local final_url=""
  local tmp_file=""
  local tmp_file_cleanup=""
  local mailcow_dir="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
  local install_dir="${MOOLIAS_INSTALL_DIR:-/opt/moolias}"
  local detected_network=""
  local detected_ipv4_cidrs=""

  command -v curl >/dev/null 2>&1 || {
    echo "Moolias installer: required command not found: curl" >&2
    exit 1
  }

  discover_mailcow_api_allowlist() {
    local nginx_id network label subnet

    command -v docker >/dev/null 2>&1 || return 0
    [[ -d "$mailcow_dir" ]] || return 0
    [[ -f "${mailcow_dir}/docker-compose.yml" ]] || return 0
    docker compose version >/dev/null 2>&1 || return 0

    nginx_id="$(
      cd "$mailcow_dir" && docker compose ps -q nginx-mailcow 2>/dev/null
    )"
    [[ -n "$nginx_id" ]] || return 0

    while IFS= read -r network; do
      [[ -n "$network" ]] || continue
      label="$(
        docker network inspect \
          --format '{{index .Labels "com.docker.compose.network"}}' \
          "$network" 2>/dev/null || true
      )"
      if [[ "$label" == "mailcow-network" ]]; then
        detected_network="$network"
        break
      fi
    done < <(
      docker inspect \
        --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
        "$nginx_id" 2>/dev/null || true
    )

    [[ -n "$detected_network" ]] || return 0

    while IFS= read -r subnet; do
      [[ -n "$subnet" ]] || continue
      [[ "$subnet" == *:* ]] && continue
      detected_ipv4_cidrs+="${detected_ipv4_cidrs:+ }${subnet}"
    done < <(
      docker network inspect \
        --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' \
        "$detected_network" 2>/dev/null || true
    )
  }

  print_mailcow_api_allowlist_guidance() {
    [[ -n "$detected_ipv4_cidrs" ]] || return 0

    cat <<EOF

============================================================
Mailcow API access
============================================================
Moolias will run inside Mailcow's Docker network:
  ${detected_network}

The recommended same-host deployment keeps browser-facing OAuth on the public
Mailcow URL while backend API/OAuth requests use nginx-mailcow:8080 directly.

Before entering the Mailcow API key, configure a READ/WRITE API key in
Mailcow and allow the following IPv4 CIDR network(s):
EOF

    local cidr
    for cidr in $detected_ipv4_cidrs; do
      printf '  %s\n' "$cidr"
    done

    cat <<'EOF'

Do not use the individual Moolias container IP; it can change after a
container recreation. Do not enable "Skip IP check for API" for the normal
same-host installation.

You can leave this installer open while you configure the API key in the
Mailcow administration interface, then paste the key when prompted.
============================================================
EOF
  }

  validate_mailcow_api_from_container() {
    local container_id

    [[ -f "${install_dir}/compose.yml" ]] || return 0
    [[ -f "${install_dir}/.env" ]] || return 0

    container_id="$(
      cd "$install_dir" && docker compose ps -q moolias 2>/dev/null || true
    )"
    [[ -n "$container_id" ]] || return 0

    echo
    echo "Validating Mailcow API access from the Moolias container..."

    if (
      cd "$install_dir"
      docker compose exec -T moolias python - <<'PY'
import os
import sys

import httpx

mailcow_url = os.environ.get("MAILCOW_URL", "").rstrip("/")
api_key = os.environ.get("MAILCOW_API_KEY", "")
verify_value = os.environ.get("MAILCOW_VERIFY_TLS", "true").strip().lower()
verify_tls = verify_value not in {"0", "false", "no", "off"}

if not mailcow_url or not api_key:
    print("Mailcow API validation: required configuration is missing.", file=sys.stderr)
    raise SystemExit(2)

try:
    response = httpx.get(
        f"{mailcow_url}/api/v1/get/domain/all",
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        verify=verify_tls,
        timeout=15.0,
    )
except httpx.HTTPError as exc:
    print(f"Mailcow API validation failed: {exc}", file=sys.stderr)
    raise SystemExit(2) from exc

if response.status_code in {401, 403}:
    print(
        f"Mailcow API validation returned HTTP {response.status_code}. "
        "Check the API key and its IP/CIDR allowlist.",
        file=sys.stderr,
    )
    raise SystemExit(3)

try:
    response.raise_for_status()
except httpx.HTTPStatusError as exc:
    print(f"Mailcow API validation failed: {exc}", file=sys.stderr)
    raise SystemExit(2) from exc

print("Mailcow API access from Moolias container: OK")
PY
    ); then
      return 0
    fi

    echo >&2
    echo "Moolias installer: Mailcow API access from the Moolias container failed." >&2
    if [[ -n "$detected_ipv4_cidrs" ]]; then
      echo "Verify that the Mailcow read/write API key allows:" >&2
      local cidr
      for cidr in $detected_ipv4_cidrs; do
        printf '  %s\n' "$cidr" >&2
      done
      echo 'and that "Skip IP check for API" is not required/enabled for this setup.' >&2
    else
      echo "Verify the Mailcow API key and its source-IP/CIDR allowlist." >&2
    fi
    return 1
  }

  if [[ -n "$requested_ref" ]]; then
    install_ref="$requested_ref"
  elif [[ -n "$source_dir" ]]; then
    install_ref="local-source"
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
  printf -v tmp_file_cleanup '%q' "$tmp_file"
  trap "rm -f -- ${tmp_file_cleanup}" EXIT

  if [[ -n "$source_dir" ]]; then
    [[ -f "${source_dir}/scripts/install.sh" ]] || {
      echo "Moolias installer: local scripts/install.sh not found in ${source_dir}." >&2
      exit 1
    }
    cp -a "${source_dir}/scripts/install.sh" "$tmp_file"
  else
    curl --proto '=https' --tlsv1.2 -fsSL \
      "${raw_base}/${install_ref}/scripts/install.sh" \
      -o "$tmp_file" \
      || {
        echo "Moolias installer: could not download installer from ${install_ref}." >&2
        exit 1
      }
  fi

  bash -n "$tmp_file" || {
    echo "Moolias installer: downloaded installer failed syntax validation." >&2
    exit 1
  }

  discover_mailcow_api_allowlist
  print_mailcow_api_allowlist_guidance

  MOOLIAS_INSTALL_REF="$install_ref" bash "$tmp_file" "$@"

  validate_mailcow_api_from_container
}

main "$@"
