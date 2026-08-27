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
  local child_stdout=""
  local child_stdout_cleanup=""
  local child_stderr=""
  local child_stderr_cleanup=""
  local tls_status_file=""
  local tls_status_file_cleanup=""
  local mailcow_dir="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
  local mailcow_conf="${mailcow_dir}/mailcow.conf"
  local install_dir="${MOOLIAS_INSTALL_DIR:-/opt/moolias}"
  local detected_network=""
  local detected_cidrs=""
  local mailcow_http_port="80"
  local mailcow_internal_url=""
  local tls_status="not-managed"
  local sender_install_mode="${MOOLIAS_INSTALL_SENDER_PROTECTION:-ask}"
  local tls_mode="${MOOLIAS_TLS_MODE:-ask}"
  local noninteractive="${MOOLIAS_NONINTERACTIVE:-false}"
  local tty_available=false
  local fresh_install=true
  local wizard_enabled=false
  local base_url=""
  local public_scheme=""
  local moolias_hostname=""
  local api_key=""
  local oauth_id=""
  local oauth_secret=""
  local access_tag=""
  local access_tag_managed=false
  local child_may_prompt=false
  local -a child_env=()

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

  record_tls_status() {
    tls_status="$1"
    if [[ -n "$tls_status_file" ]]; then
      printf '%s\n' "$tls_status" > "$tls_status_file"
    fi
  }

  open_tty() {
    [[ "$noninteractive" == "true" ]] && return 0

    if { exec 3<>/dev/tty; } 2>/dev/null; then
      tty_available=true
    fi
  }

  clear_setup_screen() {
    [[ "$wizard_enabled" == true ]] || return 0
    if [[ "${TERM:-}" != "dumb" ]]; then
      printf '\033[2J\033[H' >&3
    else
      printf '\n\n' >&3
    fi
  }

  setup_page() {
    local step="$1"
    local title="$2"

    clear_setup_screen
    printf '%s\n' \
      '============================================================' \
      " Moolias Setup                                      ${step}/6" \
      " ${title}" \
      '============================================================' \
      '' >&3
  }

  prompt_value() {
    local label="$1"
    local default_value="$2"
    local value=""

    [[ "$tty_available" == true ]] || {
      echo "Moolias installer: interactive input is unavailable." >&2
      return 1
    }

    if [[ -n "$default_value" ]]; then
      printf '%s [%s]: ' "$label" "$default_value" >&3
    else
      printf '%s: ' "$label" >&3
    fi
    IFS= read -r value <&3
    printf '%s' "${value:-$default_value}"
  }

  prompt_secret() {
    local label="$1"
    local value=""

    [[ "$tty_available" == true ]] || {
      echo "Moolias installer: interactive input is unavailable." >&2
      return 1
    }

    printf '%s: ' "$label" >&3
    IFS= read -r -s value <&3
    printf '\n' >&3
    [[ -n "$value" ]] || {
      echo "Moolias installer: ${label} must not be empty." >&2
      return 1
    }
    printf '%s' "$value"
  }

  prompt_yes_no() {
    local label="$1"
    local default_answer="$2"
    local answer=""

    [[ "$tty_available" == true ]] || {
      [[ "$default_answer" == "yes" ]]
      return
    }

    if [[ "$default_answer" == "yes" ]]; then
      printf '%s [Y/n]: ' "$label" >&3
    else
      printf '%s [y/N]: ' "$label" >&3
    fi
    IFS= read -r answer <&3
    answer="${answer:-$default_answer}"

    case "${answer,,}" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *)
        echo "Moolias installer: please answer yes or no." >&2
        return 2
        ;;
    esac
  }

  run_progress() {
    local label="$1"
    shift
    local output=""
    local pid=""
    local status=0
    local frame_index=0
    local -a frames=('|' '/' '-' $'\\')

    if [[ "$wizard_enabled" != true ]]; then
      printf '%s...\n' "$label"
      "$@"
      return
    fi

    output="$(mktemp)"
    "$@" >"$output" 2>&1 &
    pid="$!"

    while kill -0 "$pid" >/dev/null 2>&1; do
      printf '\r  %s %s' "${frames[$frame_index]}" "$label" >&3
      frame_index=$(((frame_index + 1) % ${#frames[@]}))
      sleep 0.2
    done

    if wait "$pid"; then
      status=0
    else
      status="$?"
    fi

    if [[ "$status" -eq 0 ]]; then
      printf '\r  [OK] %s\033[K\n' "$label" >&3
      rm -f "$output"
      return 0
    fi

    printf '\r  [!!] %s\033[K\n' "$label" >&3
    cat "$output" >&2
    rm -f "$output"
    return "$status"
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
      detected_cidrs+="${detected_cidrs:+ }${subnet}"
    done < <(
      docker network inspect \
        --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' \
        "$detected_network" 2>/dev/null || true
    )
  }

  print_mailcow_api_allowlist_guidance() {
    [[ -n "$detected_cidrs" ]] || return 0

    echo
    echo "Mailcow API access"
    echo "-------------------"
    echo "Docker network: ${detected_network}"
    echo "Internal Mailcow URL: ${mailcow_internal_url}"
    echo
    echo "Before entering the API key, create/use a READ/WRITE API key in Mailcow"
    echo "and allow these Docker network CIDRs:"

    local cidr
    for cidr in $detected_cidrs; do
      printf '  %s\n' "$cidr"
    done

    echo
    echo 'Leave "Skip IP check for API" disabled.'
    echo "Do not allowlist the individual Moolias container IP."
    echo
  }

  validate_base_url() {
    if [[ "$base_url" =~ ^(https?)://([A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?)(:([0-9]{1,5}))?$ ]]; then
      public_scheme="${BASH_REMATCH[1]}"
      moolias_hostname="${BASH_REMATCH[2],,}"
      return 0
    fi

    echo "Moolias installer: MOOLIAS_BASE_URL must be an http(s) origin without a path." >&2
    return 1
  }

  run_setup_wizard() {
    local mailcow_hostname domain_part default_hostname default_base_url
    local existing_env="${install_dir}/.env"
    local skip_le only_mailcow_hostname cidr

    mailcow_hostname="$(read_key_value "$mailcow_conf" MAILCOW_HOSTNAME || true)"
    [[ -n "$mailcow_hostname" ]] || {
      echo "Moolias installer: MAILCOW_HOSTNAME is missing from mailcow.conf." >&2
      return 1
    }

    domain_part="${mailcow_hostname#*.}"
    if [[ "$domain_part" == "$mailcow_hostname" ]]; then
      default_hostname="moolias.${mailcow_hostname}"
    else
      default_hostname="moolias.${domain_part}"
    fi
    default_base_url="https://${default_hostname}"

    if [[ -f "$existing_env" ]]; then
      fresh_install=false
      return 0
    fi

    fresh_install=true

    if [[ "$noninteractive" == "true" || "$tty_available" != true ]]; then
      if [[ ${MOOLIAS_ACCESS_TAG+x} ]]; then
        access_tag="${MOOLIAS_ACCESS_TAG}"
      else
        access_tag="moolias-access"
      fi
      access_tag_managed=true
      if [[ "${sender_install_mode,,}" == "ask" ]]; then
        sender_install_mode="no"
      fi
      print_mailcow_api_allowlist_guidance
      return 0
    fi

    wizard_enabled=true

    setup_page 1 "Public URL"
    printf '%s\n' \
      'Choose the public URL where users will open Moolias.' \
      'A dedicated hostname is required; do not reuse the Mailcow hostname.' \
      '' >&3
    base_url="${MOOLIAS_BASE_URL:-}"
    if [[ -z "$base_url" ]]; then
      base_url="$(prompt_value "Public Moolias URL" "$default_base_url")"
    else
      printf 'Using URL from the environment: %s\n' "$base_url" >&3
    fi
    base_url="${base_url%/}"
    validate_base_url || return 1

    setup_page 2 "Mailcow API"
    printf '%s\n' \
      'Moolias needs a Mailcow READ/WRITE API key to manage aliases.' \
      'For a same-host installation, allow the complete Mailcow Docker subnet' \
      'instead of the individual Moolias container IP.' \
      '' >&3
    if [[ -n "$detected_network" ]]; then
      printf 'Docker network:       %s\n' "$detected_network" >&3
    fi
    if [[ -n "$mailcow_internal_url" ]]; then
      printf 'Internal Mailcow URL: %s\n' "$mailcow_internal_url" >&3
    fi
    if [[ -n "$detected_cidrs" ]]; then
      printf '\nAllow these networks on the API key:\n' >&3
      for cidr in $detected_cidrs; do
        printf '  %s\n' "$cidr" >&3
      done
    fi
    printf '%s\n' \
      '' \
      'Keep "Skip IP check for API" disabled.' \
      '' >&3
    api_key="${MAILCOW_API_KEY:-}"
    if [[ -z "$api_key" ]]; then
      api_key="$(prompt_secret "Mailcow read/write API key")"
    else
      printf 'Using the API key supplied through the environment.\n' >&3
    fi

    setup_page 3 "OAuth"
    printf '%s\n' \
      'Moolias uses Mailcow OAuth2 for user login.' \
      'Create an OAuth2 client in Mailcow with this redirect URI:' \
      '' \
      "  ${base_url}/oauth/callback" \
      '' >&3
    oauth_id="${MAILCOW_OAUTH_CLIENT_ID:-}"
    if [[ -z "$oauth_id" ]]; then
      oauth_id="$(prompt_value "Mailcow OAuth client ID" "")"
    fi
    [[ -n "$oauth_id" ]] || {
      echo "Moolias installer: Mailcow OAuth client ID must not be empty." >&2
      return 1
    }
    oauth_secret="${MAILCOW_OAUTH_CLIENT_SECRET:-}"
    if [[ -z "$oauth_secret" ]]; then
      oauth_secret="$(prompt_secret "Mailcow OAuth client secret")"
    fi

    setup_page 4 "Access control"
    printf '%s\n' \
      'Moolias can restrict login access with a Mailcow tag.' \
      '' \
      'Recommended: moolias-access' \
      '' \
      'Only mailboxes or domains carrying this tag can then use Moolias.' \
      'Without an access tag, every authenticated Mailcow mailbox can log in.' \
      '' >&3
    if [[ ${MOOLIAS_ACCESS_TAG+x} ]]; then
      access_tag="${MOOLIAS_ACCESS_TAG}"
      access_tag_managed=true
      printf 'Using access-tag setting supplied through the environment.\n' >&3
    elif prompt_yes_no 'Enable access restriction with "moolias-access"?' "yes"; then
      access_tag="moolias-access"
      access_tag_managed=true
    else
      access_tag=""
      access_tag_managed=true
    fi

    setup_page 5 "TLS certificate"
    skip_le="$(read_key_value "$mailcow_conf" SKIP_LETS_ENCRYPT || true)"
    only_mailcow_hostname="$(read_key_value "$mailcow_conf" ONLY_MAILCOW_HOSTNAME || true)"
    if [[ "$public_scheme" == "http" ]]; then
      tls_mode="none"
      printf '%s\n' \
        'The selected URL uses HTTP, so Mailcow ACME is not required.' \
        '' >&3
    elif [[ "$tls_mode" != "ask" ]]; then
      printf 'Using TLS mode from the environment: %s\n\n' "$tls_mode" >&3
    elif is_true "${skip_le:-n}" || is_true "${only_mailcow_hostname:-n}"; then
      tls_mode="external"
      printf '%s\n' \
        'Mailcow ACME cannot manage an additional hostname with the current' \
        'Mailcow settings. Moolias will leave certificate handling external.' \
        '' >&3
    else
      printf '%s\n' \
        'Recommended: let Mailcow request and renew the certificate for Moolias.' \
        "The installer will add ${moolias_hostname} to ADDITIONAL_SAN." \
        '' >&3
      if prompt_yes_no "Use Mailcow ACME for ${moolias_hostname}?" "yes"; then
        tls_mode="mailcow-acme"
      else
        tls_mode="external"
      fi
    fi

    setup_page 6 "Primary sender protection"
    printf '%s\n' \
      'The Moolias Mailcow Agent is installed automatically because guided alias' \
      'creation and replacement use it for the exact-recipient first-mail bypass.' \
      '' \
      'Primary sender protection is an additional optional feature. When enabled,' \
      'a mailbox user can prevent authenticated sending with the mailbox primary' \
      'address while receiving and normal alias sending remain unchanged.' \
      '' >&3
    case "${sender_install_mode,,}" in
      ask)
        if prompt_yes_no "Enable primary sender protection?" "no"; then
          sender_install_mode="yes"
        else
          sender_install_mode="no"
        fi
        ;;
      yes|y|true|1)
        sender_install_mode="yes"
        printf 'Sender protection was enabled through the environment.\n' >&3
        ;;
      no|n|false|0)
        sender_install_mode="no"
        printf 'Sender protection was disabled through the environment.\n' >&3
        ;;
      *)
        echo "Moolias installer: MOOLIAS_INSTALL_SENDER_PROTECTION must be ask, yes or no." >&2
        return 1
        ;;
    esac

    printf '\nPress Enter to start the installation.\n' >&3
    IFS= read -r _ <&3
    clear_setup_screen
    printf '%s\n' \
      '============================================================' \
      ' Moolias Setup                                      Installing' \
      '============================================================' \
      '' \
      'Please keep this terminal open. Docker, Mailcow nginx, ACME and' \
      'the required Mailcow Agent can take a little while.' \
      '' >&3
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
      sender_install_mode="yes"
    else
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

  configure_post_install_env() {
    local env_file="${install_dir}/.env"

    [[ -f "$env_file" ]] || return 0

    if [[ -n "$mailcow_internal_url" ]]; then
      set_key_value "$env_file" MAILCOW_INTERNAL_URL "$mailcow_internal_url"
      set_key_value \
        "$env_file" \
        MOOLIAS_MAILCOW_AGENT_URL \
        "${mailcow_internal_url}/moolias-agent"
    fi

    if [[ "$access_tag_managed" == true ]]; then
      set_key_value "$env_file" MOOLIAS_ACCESS_TAG "$access_tag"
    fi

    (
      cd "$install_dir"
      COMPOSE_PROGRESS=quiet docker compose up -d --force-recreate moolias >/dev/null 2>&1
    ) || {
      echo "Moolias installer: could not recreate Moolias with final configuration." >&2
      return 1
    }

    wait_for_moolias || {
      echo "Moolias installer: Moolias did not become healthy after final configuration." >&2
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
    message = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = str(payload.get("msg", "")).strip()
    except ValueError:
        pass
    if message:
        print(f"Mailcow API rejected the request: {message}", file=sys.stderr)
    else:
        print(f"Mailcow API rejected the request with HTTP {response.status_code}", file=sys.stderr)
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
    if [[ -n "$detected_cidrs" ]]; then
      echo "The Mailcow read/write API key should allow these Docker network CIDRs:" >&2
      local cidr
      for cidr in $detected_cidrs; do
        printf '  %s\n' "$cidr" >&2
      done
      echo "If Mailcow reports a source IP outside these networks, allow its actual Docker subnet instead." >&2
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
    local current_base_url hostname additional_san wait_seconds elapsed certificate

    [[ -f "$env_file" ]] || return 0
    current_base_url="$(read_key_value "$env_file" MOOLIAS_BASE_URL || true)"
    [[ "$current_base_url" == https://* ]] || {
      record_tls_status "not-required"
      return 0
    }

    hostname="${current_base_url#https://}"
    hostname="${hostname%%/*}"
    hostname="${hostname%%:*}"
    [[ -n "$hostname" ]] || return 0

    additional_san="$(read_key_value "$mailcow_conf" ADDITIONAL_SAN || true)"
    if ! printf ',%s,' "$additional_san" | grep -Fqi ",${hostname},"; then
      record_tls_status "external-or-manual"
      return 0
    fi

    certificate="${mailcow_dir}/data/assets/ssl/cert.pem"
    wait_seconds="${MOOLIAS_TLS_WAIT_SECONDS:-90}"
    [[ "$wait_seconds" =~ ^[0-9]+$ ]] || wait_seconds=90
    (( wait_seconds > 600 )) && wait_seconds=600

    if certificate_matches_host "$certificate" "$hostname"; then
      record_tls_status "ok"
      return 0
    fi

    elapsed=0
    while (( elapsed < wait_seconds )); do
      sleep 5
      elapsed=$((elapsed + 5))
      if certificate_matches_host "$certificate" "$hostname"; then
        (
          cd "$mailcow_dir"
          docker compose exec -T nginx-mailcow nginx -s reload >/dev/null 2>&1
        ) || true
        record_tls_status "ok"
        return 0
      fi
    done

    record_tls_status "pending"
  }

  print_final_summary() {
    local env_file="${install_dir}/.env"
    local current_base_url sender_protection current_access_tag version container_id

    current_base_url="$(read_key_value "$env_file" MOOLIAS_BASE_URL || true)"
    sender_protection="$(read_key_value "$env_file" MOOLIAS_SENDER_PROTECTION || true)"
    current_access_tag="$(read_key_value "$env_file" MOOLIAS_ACCESS_TAG || true)"
    container_id="$(
      cd "$install_dir" && docker compose ps -q moolias 2>/dev/null || true
    )"
    version="$(
      docker inspect \
        -f '{{index .Config.Labels "org.opencontainers.image.version"}}' \
        "$container_id" 2>/dev/null || true
    )"

    if [[ "$wizard_enabled" == true ]]; then
      clear_setup_screen
    else
      echo
    fi
    echo "============================================================"
    echo "Moolias installation complete"
    echo "============================================================"
    echo
    echo "Application:       healthy"
    echo "Mailcow API:       OK"
    echo "Mailcow Agent:     configured"
    [[ -n "$mailcow_internal_url" ]] && echo "Internal routing:  ${mailcow_internal_url}"
    echo "Version:           ${version:-unknown}"

    if [[ -n "$current_access_tag" ]]; then
      echo "Access control:    tag ${current_access_tag}"
    else
      echo "Access control:    all authenticated Mailcow mailboxes"
    fi

    if is_true "${sender_protection:-false}"; then
      echo "Sender protection: enabled"
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
    echo "URL: ${current_base_url}"
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

  open_tty

  if [[ -f "${install_dir}/.env" ]]; then
    fresh_install=false
  fi

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
  child_stdout="$(mktemp)"
  child_stderr="$(mktemp)"
  tls_status_file="$(mktemp)"
  printf -v tmp_file_cleanup '%q' "$tmp_file"
  printf -v child_stdout_cleanup '%q' "$child_stdout"
  printf -v child_stderr_cleanup '%q' "$child_stderr"
  printf -v tls_status_file_cleanup '%q' "$tls_status_file"
  trap "rm -f -- ${tmp_file_cleanup} ${child_stdout_cleanup} ${child_stderr_cleanup} ${tls_status_file_cleanup}" EXIT

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
  run_setup_wizard
  resolve_sender_install_mode

  if [[ ${MOOLIAS_ACCESS_TAG+x} ]]; then
    access_tag="${MOOLIAS_ACCESS_TAG}"
    access_tag_managed=true
  elif [[ "$fresh_install" == true && "$access_tag_managed" != true ]]; then
    access_tag="moolias-access"
    access_tag_managed=true
  fi

  if [[ -z "$base_url" ]]; then
    base_url="${MOOLIAS_BASE_URL:-}"
  fi
  if [[ -z "$api_key" ]]; then
    api_key="${MAILCOW_API_KEY:-}"
  fi
  if [[ -z "$oauth_id" ]]; then
    oauth_id="${MAILCOW_OAUTH_CLIENT_ID:-}"
  fi
  if [[ -z "$oauth_secret" ]]; then
    oauth_secret="${MAILCOW_OAUTH_CLIENT_SECRET:-}"
  fi

  if [[ "$sender_install_mode" =~ ^(yes|y|true|1)$ ]]; then
    legacy_pcre="${mailcow_dir}/data/conf/postfix/blocked_sender_login.pcre"
    if [[ -s "$legacy_pcre" ]] \
      && grep -Ev '^[[:space:]]*(#|$)' "$legacy_pcre" >/dev/null 2>&1; then
      child_may_prompt=true
    fi
  fi

  child_env=(
    "MOOLIAS_INSTALL_REF=${install_ref}"
    "MOOLIAS_INSTALL_SENDER_PROTECTION=${sender_install_mode}"
    "MOOLIAS_TLS_MODE=${tls_mode}"
    "COMPOSE_PROGRESS=quiet"
  )
  [[ -n "$base_url" ]] && child_env+=("MOOLIAS_BASE_URL=${base_url}")
  [[ -n "$api_key" ]] && child_env+=("MAILCOW_API_KEY=${api_key}")
  [[ -n "$oauth_id" ]] && child_env+=("MAILCOW_OAUTH_CLIENT_ID=${oauth_id}")
  [[ -n "$oauth_secret" ]] && child_env+=("MAILCOW_OAUTH_CLIENT_SECRET=${oauth_secret}")

  run_child_install() {
    env "${child_env[@]}" \
      bash "$tmp_file" "$@" \
      >"$child_stdout" 2>"$child_stderr"
  }

  child_status=0
  if [[ "$wizard_enabled" == true && "$child_may_prompt" != true ]]; then
    set +e
    run_progress \
      "Installing Moolias and applying Mailcow/ACME changes" \
      run_child_install "$@"
    child_status="$?"
    set -e
  else
    if [[ "$wizard_enabled" == true ]]; then
      printf '%s\n' \
        'Existing sender-login rules were detected.' \
        'The installer may ask one additional question while configuring protection.' \
        '' >&3
    fi
    set +e
    run_child_install "$@"
    child_status="$?"
    set -e
  fi

  if [[ "$child_status" -ne 0 ]]; then
    if [[ -s "$child_stdout" ]]; then
      filter_installer_output < "$child_stdout" >&2
    fi
    print_child_failure "$child_stderr"
    echo "Moolias installer: installation failed." >&2
    exit "$child_status"
  fi

  if [[ "$wizard_enabled" != true && -s "$child_stdout" ]]; then
    filter_installer_output < "$child_stdout"
  fi

  run_progress "Applying final private-network and access settings" configure_post_install_env
  run_progress "Validating Mailcow API access" validate_mailcow_api_from_container
  run_progress "Checking Mailcow TLS certificate" wait_for_mailcow_tls
  if [[ -s "$tls_status_file" ]]; then
    tls_status="$(tail -n1 "$tls_status_file")"
  fi
  print_final_summary
}

main "$@"
