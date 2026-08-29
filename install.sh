#!/usr/bin/env bash
set -euo pipefail

MOOLIAS_BOOTSTRAP_CORE_TMP_CLEANUP=""
MOOLIAS_NEWSLETTER_TMP_CLEANUP=""

cleanup_install_wrapper() {
  [[ -z "${MOOLIAS_BOOTSTRAP_CORE_TMP_CLEANUP:-}" ]] \
    || rm -f -- "$MOOLIAS_BOOTSTRAP_CORE_TMP_CLEANUP"
  [[ -z "${MOOLIAS_NEWSLETTER_TMP_CLEANUP:-}" ]] \
    || rm -f -- "$MOOLIAS_NEWSLETTER_TMP_CLEANUP"
}
trap cleanup_install_wrapper EXIT

main() {
  local repository="${MOOLIAS_REPOSITORY:-vain90/Moolias}"
  local raw_base="https://raw.githubusercontent.com/${repository}"
  local latest_url="https://github.com/${repository}/releases/latest"
  local requested_ref="${MOOLIAS_INSTALL_REF:-}"
  local source_dir="${MOOLIAS_SOURCE_DIR:-}"
  local install_dir="${MOOLIAS_INSTALL_DIR:-/opt/moolias}"
  local newsletter_mode="${MOOLIAS_INSTALL_NEWSLETTER:-ask}"
  local noninteractive="${MOOLIAS_NONINTERACTIVE:-false}"
  local resolved_ref=""
  local base_core=""
  local script_dir=""
  local base_core_tmp=""
  local newsletter_bootstrap=""
  local newsletter_tmp=""
  local fresh_install=false
  local answer=""

  fail() {
    echo "Moolias installer: $*" >&2
    exit 1
  }

  command -v bash >/dev/null 2>&1 || fail "bash is required."
  command -v curl >/dev/null 2>&1 || fail "curl is required."
  command -v mktemp >/dev/null 2>&1 || fail "mktemp is required."

  [[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] \
    || fail "MOOLIAS_REPOSITORY must use owner/repository form."

  case "${newsletter_mode,,}" in
    ask|yes|y|true|1|no|n|false|0) ;;
    *) fail "MOOLIAS_INSTALL_NEWSLETTER must be ask, yes or no." ;;
  esac

  if [[ ! -f "${install_dir}/.env" ]]; then
    fresh_install=true
  fi

  fetch_to() {
    local ref="$1"
    local path="$2"
    local destination="$3"
    curl --proto '=https' --tlsv1.2 -fsSL \
      "${raw_base}/${ref}/${path}" \
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

  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"

  if [[ -n "${MOOLIAS_BOOTSTRAP_CORE_PATH:-}" ]]; then
    base_core="$MOOLIAS_BOOTSTRAP_CORE_PATH"
    [[ -f "$base_core" ]] || fail "bootstrap core not found: $base_core"
    resolved_ref="${requested_ref:-local-core}"
  elif [[ -n "$source_dir" ]]; then
    base_core="${source_dir}/scripts/install-bootstrap-core.sh"
    [[ -f "$base_core" ]] || fail "local bootstrap core is missing: $base_core"
    resolved_ref="local-source"
  elif [[ -n "$requested_ref" ]]; then
    [[ "$requested_ref" =~ ^[A-Za-z0-9._/+:-]+$ ]] \
      || fail "MOOLIAS_INSTALL_REF contains unsupported characters."
    base_core_tmp="$(mktemp)"
    MOOLIAS_BOOTSTRAP_CORE_TMP_CLEANUP="$base_core_tmp"
    if ! fetch_to "$requested_ref" "scripts/install-bootstrap-core.sh" "$base_core_tmp"; then
      # Explicit pins to releases before v1.3.1 do not contain the split core.
      # Run that release's original bootstrap unchanged.
      fetch_to "$requested_ref" "install.sh" "$base_core_tmp" \
        || fail "could not download the Moolias installer from ${requested_ref}."
    fi
    base_core="$base_core_tmp"
    resolved_ref="$requested_ref"
  elif [[ -n "$script_dir" && -f "${script_dir}/scripts/install-bootstrap-core.sh" ]]; then
    source_dir="$script_dir"
    base_core="${script_dir}/scripts/install-bootstrap-core.sh"
    resolved_ref="local-source"
  else
    local latest_ref=""
    latest_ref="$(resolve_latest_ref || true)"
    base_core_tmp="$(mktemp)"
    MOOLIAS_BOOTSTRAP_CORE_TMP_CLEANUP="$base_core_tmp"
    if [[ -n "$latest_ref" ]] \
      && fetch_to "$latest_ref" "scripts/install-bootstrap-core.sh" "$base_core_tmp"; then
      resolved_ref="$latest_ref"
    else
      # During the first rollout of this wrapper, the latest stable release can
      # predate install-bootstrap-core.sh. Use the matching main installer core;
      # the application image itself still remains on the stable latest channel.
      fetch_to "main" "scripts/install-bootstrap-core.sh" "$base_core_tmp" \
        || fail "could not download the Moolias installer core."
      resolved_ref="main"
    fi
    base_core="$base_core_tmp"
  fi

  bash -n "$base_core" || fail "downloaded Moolias installer core failed syntax validation."

  if [[ "$resolved_ref" == "local-source" ]]; then
    MOOLIAS_INSTALL_REF="${requested_ref:-local-source}" \
      MOOLIAS_SOURCE_DIR="$source_dir" \
      bash "$base_core" "$@"
  elif [[ "$resolved_ref" == "local-core" ]]; then
    bash "$base_core" "$@"
  else
    MOOLIAS_INSTALL_REF="$resolved_ref" \
      bash "$base_core" "$@"
  fi

  if [[ "${newsletter_mode,,}" == "ask" ]]; then
    if [[ "$fresh_install" == true && "$noninteractive" != "true" \
      && -r /dev/tty && -w /dev/tty ]]; then
      printf '\nEnable optional Newsletter Management now? [y/N] ' > /dev/tty
      IFS= read -r answer < /dev/tty || answer=""
      case "${answer,,}" in
        y|yes|j|ja) newsletter_mode="yes" ;;
        *) newsletter_mode="no" ;;
      esac
    else
      newsletter_mode="no"
    fi
  fi

  case "${newsletter_mode,,}" in
    yes|y|true|1) newsletter_mode="yes" ;;
    *) newsletter_mode="no" ;;
  esac

  if [[ "$newsletter_mode" == "yes" ]]; then
    if [[ -n "${MOOLIAS_NEWSLETTER_INSTALLER_PATH:-}" ]]; then
      newsletter_bootstrap="$MOOLIAS_NEWSLETTER_INSTALLER_PATH"
      [[ -f "$newsletter_bootstrap" ]] \
        || fail "Newsletter installer not found: $newsletter_bootstrap"
    elif [[ -n "$source_dir" ]]; then
      newsletter_bootstrap="${source_dir}/install-newsletter.sh"
      [[ -f "$newsletter_bootstrap" ]] \
        || fail "local Newsletter installer is missing: $newsletter_bootstrap"
    else
      newsletter_tmp="$(mktemp)"
      MOOLIAS_NEWSLETTER_TMP_CLEANUP="$newsletter_tmp"
      fetch_to "$resolved_ref" "install-newsletter.sh" "$newsletter_tmp" \
        || fail "could not download Newsletter Management installer from ${resolved_ref}."
      newsletter_bootstrap="$newsletter_tmp"
    fi

    bash -n "$newsletter_bootstrap" \
      || fail "Newsletter Management installer failed syntax validation."

    echo
    echo "Installing optional Newsletter Management..."
    if [[ "$resolved_ref" == "local-source" ]]; then
      MOOLIAS_DIR="$install_dir" \
        MOOLIAS_INSTALL_REF="${requested_ref:-local-source}" \
        MOOLIAS_SOURCE_DIR="$source_dir" \
        bash "$newsletter_bootstrap"
    elif [[ "$resolved_ref" == "local-core" ]]; then
      MOOLIAS_DIR="$install_dir" \
        bash "$newsletter_bootstrap"
    else
      MOOLIAS_DIR="$install_dir" \
        MOOLIAS_INSTALL_REF="$resolved_ref" \
        bash "$newsletter_bootstrap"
    fi
  fi
}

main "$@"
