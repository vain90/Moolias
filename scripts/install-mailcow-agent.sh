#!/usr/bin/env bash
set -euo pipefail

MOOLIAS_AGENT_CORE_TMP_CLEANUP=""
MOOLIAS_AGENT_PATCHED_CORE_CLEANUP=""

cleanup_agent_wrapper() {
  [[ -z "${MOOLIAS_AGENT_CORE_TMP_CLEANUP:-}" ]] \
    || rm -f -- "$MOOLIAS_AGENT_CORE_TMP_CLEANUP"
  [[ -z "${MOOLIAS_AGENT_PATCHED_CORE_CLEANUP:-}" ]] \
    || rm -f -- "$MOOLIAS_AGENT_PATCHED_CORE_CLEANUP"
}
trap cleanup_agent_wrapper EXIT

main() {
  local repository="${MOOLIAS_REPOSITORY:-vain90/Moolias}"
  local raw_base="https://raw.githubusercontent.com/${repository}"
  local latest_url="https://github.com/${repository}/releases/latest"
  local requested_ref="${MOOLIAS_INSTALL_REF:-}"
  local source_dir="${MOOLIAS_SOURCE_DIR:-}"
  local mailcow_dir="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
  local agent_image="${MOOLIAS_AGENT_IMAGE:-ghcr.io/vain90/moolias:edge}"
  local core_path=""
  local script_dir=""
  local core_tmp=""
  local patched_core=""
  local status=0

  fail() {
    echo "Moolias Mailcow Agent installer: $*" >&2
    exit 1
  }

  command -v bash >/dev/null 2>&1 || fail "bash is required."
  command -v curl >/dev/null 2>&1 || fail "curl is required."
  command -v docker >/dev/null 2>&1 || fail "Docker is required."
  command -v mktemp >/dev/null 2>&1 || fail "mktemp is required."

  [[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] \
    || fail "MOOLIAS_REPOSITORY must use owner/repository form."

  heal_legacy_hook_backups() {
    local hook_dir
    for hook_dir in \
      "${mailcow_dir}/data/hooks/postfix" \
      "${mailcow_dir}/data/hooks/rspamd"; do
      [[ -d "$hook_dir" ]] || continue
      find "$hook_dir" \
        -maxdepth 1 \
        -type f \
        -name 'moolias-*.before-moolias-agent-*.bak' \
        -perm /111 \
        -exec chmod a-x {} +
    done
  }

  fetch_core() {
    local ref="$1"
    local destination="$2"
    curl --proto '=https' --tlsv1.2 -fsSL \
      "${raw_base}/${ref}/scripts/install-mailcow-agent-core.sh" \
      -o "$destination"
  }

  resolve_latest_ref() {
    local final_url latest_ref
    final_url="$(
      curl --proto '=https' --tlsv1.2 -fsSL \
        -o /dev/null \
        -w '%{url_effective}' \
        "$latest_url"
    )" || return 1
    latest_ref="${final_url##*/}"
    [[ "$latest_ref" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([+][0-9A-Za-z.-]+)?$ ]] || return 1
    printf '%s' "$latest_ref"
  }

  heal_legacy_hook_backups

  if [[ "${MOOLIAS_AGENT_WRAPPER_SKIP_PULL:-false}" != "true" && "$agent_image" == */* ]]; then
    docker pull "$agent_image"
  fi

  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"

  if [[ -n "${MOOLIAS_AGENT_CORE_PATH:-}" ]]; then
    core_path="$MOOLIAS_AGENT_CORE_PATH"
    [[ -f "$core_path" ]] || fail "Agent installer core not found: $core_path"
  elif [[ -n "$source_dir" ]]; then
    core_path="${source_dir}/scripts/install-mailcow-agent-core.sh"
    [[ -f "$core_path" ]] || fail "local Agent installer core is missing: $core_path"
  elif [[ -n "$script_dir" && -f "${script_dir}/install-mailcow-agent-core.sh" ]]; then
    core_path="${script_dir}/install-mailcow-agent-core.sh"
  elif [[ -n "${MOOLIAS_AGENT_CORE_URL:-}" ]]; then
    core_tmp="$(mktemp)"
    MOOLIAS_AGENT_CORE_TMP_CLEANUP="$core_tmp"
    curl -fsSL "$MOOLIAS_AGENT_CORE_URL" -o "$core_tmp" \
      || fail "could not download the Mailcow Agent installer core."
    core_path="$core_tmp"
  elif [[ -n "$requested_ref" ]]; then
    [[ "$requested_ref" =~ ^[A-Za-z0-9._/+:-]+$ ]] \
      || fail "MOOLIAS_INSTALL_REF contains unsupported characters."
    core_tmp="$(mktemp)"
    MOOLIAS_AGENT_CORE_TMP_CLEANUP="$core_tmp"
    fetch_core "$requested_ref" "$core_tmp" \
      || fail "could not download the Mailcow Agent installer core from ${requested_ref}."
    core_path="$core_tmp"
  else
    local latest_ref=""
    latest_ref="$(resolve_latest_ref || true)"
    core_tmp="$(mktemp)"
    MOOLIAS_AGENT_CORE_TMP_CLEANUP="$core_tmp"
    if [[ -n "$latest_ref" ]] && fetch_core "$latest_ref" "$core_tmp"; then
      :
    else
      fetch_core "main" "$core_tmp" \
        || fail "could not download the Mailcow Agent installer core."
    fi
    core_path="$core_tmp"
  fi

  patched_core="$(mktemp)"
  MOOLIAS_AGENT_PATCHED_CORE_CLEANUP="$patched_core"
  if ! awk '
    {
      print
      if ($0 == "    cp -a \"$path\" \"${path}.before-moolias-agent-${stamp}.bak\"") {
        print "    case \"$path\" in"
        print "      \"$POSTFIX_HOOK_DIR\"/*|\"$RSPAMD_HOOK_DIR\"/*)"
        print "        chmod a-x \"${path}.before-moolias-agent-${stamp}.bak\""
        print "        ;;"
        print "    esac"
        injected++
      }
    }
    END {
      if (injected != 1) exit 42
    }
  ' "$core_path" > "$patched_core"; then
    fail "Agent installer core did not match the expected safe backup hook point."
  fi

  bash -n "$patched_core" \
    || fail "patched Mailcow Agent installer core failed syntax validation."

  set +e
  MOOLIAS_AGENT_IMAGE="$agent_image" bash "$patched_core" "$@"
  status="$?"
  set -e

  heal_legacy_hook_backups
  return "$status"
}

main "$@"
