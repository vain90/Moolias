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
  local child_stderr=""
  local child_stderr_cleanup=""
  local mailcow_dir="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
  local mailcow_conf="${mailcow_dir}/mailcow.conf"
  local install_dir="${MOOLIAS_INSTALL_DIR:-/opt/moolias}"
  local detected_network=""
  local detected_ipv4_cidrs=""
  local mailcow_http_port="80"
  local mailcow_internal_url=""
  local tls_status="not-managed"
  local sender_install_mode="${MOOLIAS_INSTALL_SENDER_PROTECTION:-ask}"

  command -v awk >/dev/null 2>&1 || {
    echo "Moolias installer: required command not found: awk" >&2
    exit 1
  }
  command -v curl >/dev/null 2>&1 || {
    echo "Moolias installer: required command not found: curl" >&2
    exit 1
  }
  command -v mktemp >/dev/null 2>&1 || {
    echo "Moolias installer: required command not found: mktemp" >&2
    exit 1
  }

  read_key_value() {
    local file="$1"
    local key="$2"
    local value

    value="$(
      awk -v key="$key" '
        index($0, key "=") == 1 {
          print substr($0, length(key) + 2)
          found = 1
        }
        END { if (!found) exit 1 }
      ' "$file" 2>/dev/null | tail -n1
    )" || return 1

    value="${value%$'\r'}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    printf '%s' "$value"
  }

  set_key_value() {
    local file="$1"
    local key="$2"
    local value="$3"
    local tmp

    [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || {
      echo "Moolias installer: ${key} must be a single-line value." >&2
      return 1
    }

    tmp="$(mktemp "${file}.moolias.XXXXXX")"
    awk -v key="$key" -v value="$value" '
      BEGIN { replaced = 0 }
      index($0, key "=") == 1 {
        if (!replaced) {
          print key "=" value
          replaced = 1
        }
        next
      }
      { print }
      END {
        if (!replaced) {
          print key "=" value
        }
      }
    ' "$file" > "$tmp"

    chmod --reference="$file" "$tmp" 2>/dev/null || chmod 0600 "$tmp"
    chown --reference="$file" "$tmp" 2>/dev/null || true
    mv "$tmp" "$file"
  }

  is_true() {
    case "${1,,}" in
      1|true|yes|y|on) return 0 ;;
      *) return 1 ;;
    esac
  }

  discover_mailcow_environment() {
    local nginx_id network label subnet configured_port

    command -v docker >/dev/null 2>&1 || return 0
    [[ -d "$mailcow_dir" ]] || return 0
    [[ -f "${mailcow_dir}/docker-compose.yml" ]] || return 0
    [[ -f "$mailcow_conf" ]] || return 0
    docker compose version >/dev/null 2>&1 || return 0

    configured_port="$(read_key_value "$mailcow_conf" HTTP_PORT || true)"
    if [[ -n "$configured_port" ]]; then
      if [[ "$configured_port" =~ ^[0-9]+$ ]] \
        && (( configured_port >= 1 && configured_port <= 65535 )); then
        mailcow_http_port="$configured_port"
      else
        echo "Moolias installer: invalid HTTP_PORT in mailcow.conf: ${configured_port}" >&2
        exit 1
      fi
    fi

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
    mailcow_internal_url="http://nginx-mailcow:${mailcow_http_port}"

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

    echo
    echo "Mailcow API access"
    echo "-------------------"
    echo "Docker network: ${detected_network}"
    echo "Internal Mailcow URL: ${mailcow_internal_url}"
    echo
    echo "Before entering the API key, create/use a READ/WRITE API key in Mailcow"
    echo "and allow this Docker network:"

    local cidr
    for cidr in $detected_ipv4_cidrs; do
      printf '  %s\n' "$cidr"
    done

    echo
    echo 'Leave "Skip IP check for API" disabled.'
    echo "Do not allowlist the individual Moolias container IP."
    echo
  }

  resolve_sender_install_mode() {
    local env_file="${install_dir}/.env"
    local current=""

    case "${sender_install_mode,,}" in
      ask|yes|y|true|1|no|n|false|0) ;;
      *)
        echo "Moolias installer: MOOLIAS_INSTALL_SENDER_PROTECTION must be ask, yes or no." >&2
        exit 1
        ;;
    esac

    [[ "${sender_install_mode,,}" == "ask" ]] || return 0
    [[ -f "$env_file" ]] || return 0

    current="$(read_key_value "$env_file" MOOLIAS_SENDER_PROTECTION || true)"
    if is_true "${current:-false}"; then
      # Sender protection is already configured. A normal installer rerun must
      # preserve it instead of asking the child installer to install it again.
      sender_install_mode="no"
    fi
  }

  filter_installer_output() {
    awk '
      function divider(line) { return line ~ /^={20,}$/ }
      function hidden_title(line) {
        return line == "Moolias Mailcow Agent installed successfully" \
          || line == "Moolias installed successfully"
      }
      {
        if (hide) {
          if (divider($0)) {
            hidden_dividers++
            if (hidden_dividers >= 2) {
              hide = 0
              hidden_dividers = 0
            }
          }
          next
        }

        if (hidden_title($0)) {
          if (divider(previous)) {
            previous = ""
          }
          hide = 1
          hidden_dividers = 0
          next
        }

        if (previous != "") {
          print previous
          fflush()
        }
        previous = $0
      }
      END {
        if (!hide && previous != "") {
          print previous
        }
      }
    '
  }

  print_child_failure() {
    local path="$1"
    [[ -s "$path" ]] || return 0

    # Successful nginx validation/reload messages are noisy and may precede an
    # unrelated later installer failure. Keep actual nginx errors, but omit only
    # known warning/success chatter from the failure report.
    awk '
      /nginx: \[warn\]/ { next }
      /\[warn\].*listen .* http2.*deprecated/ { next }
      /\[warn\].*conflicting server name/ { next }
      /nginx: the configuration file .* syntax is ok/ { next }
      /nginx: configuration file .* test is successful/ { next }
      /\[notice\].*signal process started/ { next }
      { print }
    ' "$path" >&2
  }

  wait_for_moolias() {
    local container_id state

    for _ in $(seq 1 45); do
      container_id="$(
        cd "$install_dir" && docker compose ps -q moolias 2>/dev/null || true
      )"
      if [[ -n "$container_id" ]]; then
        state="$(
          docker inspect \
            --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
            "$container_id" 2>/dev/null || true
        )"
        case "$state" in
          healthy) return 0 ;;
          unhealthy|exited|dead) return 1 ;;
        esac
      fi
      sleep 2
    done
    return 1
  }

  configure_internal_mailcow_url() {
    local env_file="${install_dir}/.env"
    local sender_protection

    [[ -n "$mailcow_internal_url" ]] || return 0
    [[ -f "$env_file" ]] || return 0

    set_key_value "$env_file" MAILCOW_INTERNAL_URL "$mailcow_internal_url"

    sender_protection="$(read_key_value "$env_file" MOOLIAS_SENDER_PROTECTION || true)"
    if is_true "${sender_protection:-false}"; then
      set_key_value \
        "$env_file" \
        MOOLIAS_SENDER_AGENT_URL \
        "${mailcow_internal_url}/moolias-agent"
    fi

    (
      cd "$install_dir"
      COMPOSE_PROGRESS=quiet docker compose up -d --force-recreate moolias >/dev/null 2>&1
    ) || {
      echo "Moolias installer: could not recreate Moolias with internal Mailcow routing." >&2
      return 1
    }

    wait_for_moolias || {
      echo "Moolias installer: Moolias did not become healthy after configuring internal Mailcow routing." >&2
      return 1
    }
  }

  validate_mailcow_api_from_container() {
    local container_id

    [[ -f "${install_dir}/compose.yml" ]] || return 0
    [[ -f "${install_dir}/.env" ]] || return 0

    container_id="$(
      cd "$install_dir" && docker compose ps -q moolias 2>/dev/null || true
    )"
    [[ -n "$container_id" ]] || return 0

    if (
      cd "$install_dir"
      docker compose exec -T moolias python - <<'PY'
import os
import sys

import httpx

mailcow_url = (
    os.environ.get("MAILCOW_INTERNAL_URL")
    or os.environ.get("MAILCOW_URL", "")
).rstrip("/")
api_key = os.environ.get("MAILCOW_API_KEY", "")
verify_value = os.environ.get("MAILCOW_VERIFY_TLS", "true").strip().lower()
verify_tls = verify_value not in {"0", "false", "no", "off"}

if not mailcow_url or not api_key:
    print("required Mailcow API configuration is missing", file=sys.stderr)
    raise SystemExit(2)

try:
    response = httpx.get(
        f"{mailcow_url}/api/v1/get/domain/all",
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        verify=verify_tls,
        timeout=15.0,
    )
except httpx.HTTPError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2) from exc

if response.status_code in {401, 403}:
    print(f"HTTP {response.status_code}", file=sys.stderr)
    raise SystemExit(3)

try:
    response.raise_for_status()
except httpx.HTTPStatusError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2) from exc
PY
    ); then
      return 0
    fi

    echo >&2
    echo "Moolias installer: Mailcow API validation failed." >&2
    if [[ -n "$detected_ipv4_cidrs" ]]; then
      echo "Verify that the Mailcow read/write API key allows:" >&2
      local cidr
      for cidr in $detected_ipv4_cidrs; do
        printf '  %s\n' "$cidr" >&2
      done
    fi
    if [[ -n "$mailcow_internal_url" ]]; then
      echo "Internal Mailcow URL: ${mailcow_internal_url}" >&2
    fi
    return 1
  }

  certificate_matches_host() {
    local certificate="$1"
    local hostname="$2"

    command -v openssl >/dev/null 2>&1 || return 1
    [[ -s "$certificate" ]] || return 1

    openssl x509 \
      -in "$certificate" \
      -noout \
      -checkhost "$hostname" >/dev/null 2>&1 \
      && openssl x509 \
        -in "$certificate" \
        -noout \
        -checkend 0 >/dev/null 2>&1
  }

  wait_for_mailcow_tls() {
    local env_file="${install_dir}/.env"
    local base_url hostname additional_san wait_seconds elapsed certificate

    [[ -f "$env_file" ]] || return 0
    base_url="$(read_key_value "$env_file" MOOLIAS_BASE_URL || true)"
    [[ "$base_url" == https://* ]] || {
      tls_status="not-required"
      return 0
    }

    hostname="${base_url#https://}"
    hostname="${hostname%%/*}"
    hostname="${hostname%%:*}"
    [[ -n "$hostname" ]] || return 0

    additional_san="$(read_key_value "$mailcow_conf" ADDITIONAL_SAN || true)"
    if ! printf ',%s,' "$additional_san" | grep -Fqi ",${hostname},"; then
      tls_status="external-or-manual"
      return 0
    fi

    certificate="${mailcow_dir}/data/assets/ssl/cert.pem"
    wait_seconds="${MOOLIAS_TLS_WAIT_SECONDS:-90}"
    [[ "$wait_seconds" =~ ^[0-9]+$ ]] || wait_seconds=90
    (( wait_seconds > 600 )) && wait_seconds=600

    if certificate_matches_host "$certificate" "$hostname"; then
      tls_status="ok"
      return 0
    fi

    echo "Waiting for Mailcow ACME certificate for ${hostname} (up to ${wait_seconds}s)..."
    elapsed=0
    while (( elapsed < wait_seconds )); do
      sleep 5
      elapsed=$((elapsed + 5))
      if certificate_matches_host "$certificate" "$hostname"; then
        (
          cd "$mailcow_dir"
          docker compose exec -T nginx-mailcow nginx -s reload >/dev/null 2>&1
        ) || true
        tls_status="ok"
        return 0
      fi
    done

    tls_status="pending"
  }

  print_final_summary() {
    local env_file="${install_dir}/.env"
    local base_url sender_protection version container_id

    base_url="$(read_key_value "$env_file" MOOLIAS_BASE_URL || true)"
    sender_protection="$(read_key_value "$env_file" MOOLIAS_SENDER_PROTECTION || true)"
    container_id="$(
      cd "$install_dir" && docker compose ps -q moolias 2>/dev/null || true
    )"
    version="$(
      docker inspect \
        -f '{{index .Config.Labels "org.opencontainers.image.version"}}' \
        "$container_id" 2>/dev/null || true
    )"

    echo
    echo "============================================================"
    echo "Moolias installation complete"
    echo "============================================================"
    echo
    echo "Application:       healthy"
    echo "Mailcow API:       OK"
    [[ -n "$mailcow_internal_url" ]] && echo "Internal routing:  ${mailcow_internal_url}"
    echo "Version:           ${version:-unknown}"

    if is_true "${sender_protection:-false}"; then
      echo "Sender protection: enabled"
      echo "Agent secret:      saved automatically in ${env_file}"
      echo "                   No copy/paste is required."
    else
      echo "Sender protection: disabled"
    fi

    case "$tls_status" in
      ok) echo "TLS certificate:   OK" ;;
      pending) echo "TLS certificate:   PENDING" ;;
      not-required) echo "TLS certificate:   not required for HTTP deployment" ;;
      external-or-manual) echo "TLS certificate:   managed externally/manually" ;;
      *) echo "TLS certificate:   not checked" ;;
    esac

    echo
    echo "URL: ${base_url}"
    echo "Installation: ${install_dir}"
    echo
    echo "Update later with:"
    echo "  cd ${install_dir} && ./update.sh"

    if [[ "$tls_status" == "pending" ]]; then
      echo
      echo "IMPORTANT: Do not bypass the browser certificate warning yet."
      echo "Mailcow ACME has not activated a certificate containing the Moolias hostname."
      echo "Check ACME with:"
      echo "  cd ${mailcow_dir} && docker compose logs --tail=50 acme-mailcow"
    fi

    echo "============================================================"
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
        "Using installer files from main; the application image remains on the stable latest channel."
    fi
  fi

  if [[ ! "$install_ref" =~ ^[A-Za-z0-9._/+:-]+$ ]]; then
    echo "Moolias installer: MOOLIAS_INSTALL_REF contains unsupported characters." >&2
    exit 1
  fi

  tmp_file="$(mktemp)"
  child_stderr="$(mktemp)"
  printf -v tmp_file_cleanup '%q' "$tmp_file"
  printf -v child_stderr_cleanup '%q' "$child_stderr"
  trap "rm -f -- ${tmp_file_cleanup} ${child_stderr_cleanup}" EXIT

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

  discover_mailcow_environment
  print_mailcow_api_allowlist_guidance
  resolve_sender_install_mode

  set +e
  MOOLIAS_INSTALL_REF="$install_ref" \
    MOOLIAS_INSTALL_SENDER_PROTECTION="$sender_install_mode" \
    COMPOSE_PROGRESS=quiet \
    bash "$tmp_file" "$@" \
      2>"$child_stderr" \
      | filter_installer_output
  child_status="${PIPESTATUS[0]}"
  set -e

  if [[ "$child_status" -ne 0 ]]; then
    print_child_failure "$child_stderr"
    echo "Moolias installer: installation failed." >&2
    exit "$child_status"
  fi

  configure_internal_mailcow_url
  validate_mailcow_api_from_container
  wait_for_mailcow_tls
  print_final_summary
}

main "$@"
