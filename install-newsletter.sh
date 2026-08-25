#!/usr/bin/env bash
set -euo pipefail

main() {
  local repository="${MOOLIAS_REPOSITORY:-vain90/Moolias}"
  local raw_base="https://raw.githubusercontent.com/${repository}"
  local latest_url="https://github.com/${repository}/releases/latest"
  local requested_ref="${MOOLIAS_INSTALL_REF:-}"
  local source_dir="${MOOLIAS_SOURCE_DIR:-}"
  local install_ref=""
  local final_url=""
  local latest_ref=""
  local tmp_dir=""

  fail() {
    echo "Moolias Newsletter installer: $*" >&2
    exit 1
  }

  command -v curl >/dev/null 2>&1 || fail "curl is required."
  command -v mktemp >/dev/null 2>&1 || fail "mktemp is required."
  command -v bash >/dev/null 2>&1 || fail "bash is required."

  [[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] \
    || fail "MOOLIAS_REPOSITORY must use owner/repository form."

  if [[ -n "$source_dir" ]]; then
    install_ref="local-source"
  elif [[ -n "$requested_ref" ]]; then
    install_ref="$requested_ref"
  else
    final_url="$(
      curl --proto '=https' --tlsv1.2 -fsSL \
        -o /dev/null \
        -w '%{url_effective}' \
        "$latest_url"
    )" || fail "could not determine the latest stable Moolias release."

    latest_ref="${final_url##*/}"
    [[ "$latest_ref" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([+][0-9A-Za-z.-]+)?$ ]] \
      || fail "unexpected latest release tag: ${latest_ref}"
    install_ref="$latest_ref"
  fi

  if [[ "$install_ref" != "local-source" && ! "$install_ref" =~ ^[A-Za-z0-9._/+:-]+$ ]]; then
    fail "MOOLIAS_INSTALL_REF contains unsupported characters."
  fi

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf -- "$tmp_dir"' EXIT
  mkdir -p "${tmp_dir}/scripts/rspamd"

  fetch_asset() {
    local path="$1"
    local destination="$2"

    if [[ -n "$source_dir" ]]; then
      [[ -f "${source_dir}/${path}" ]] \
        || fail "local source file is missing: ${source_dir}/${path}"
      cp -a "${source_dir}/${path}" "$destination"
      return 0
    fi

    curl --proto '=https' --tlsv1.2 -fsSL \
      "${raw_base}/${install_ref}/${path}" \
      -o "$destination" \
      || fail "could not download ${path} from ${install_ref}. The selected stable release may not support Newsletter Management."
  }

  fetch_asset \
    "scripts/install-newsletter-agent.sh" \
    "${tmp_dir}/scripts/install-newsletter-agent.sh"
  fetch_asset \
    "scripts/install-newsletter-rspamd.sh" \
    "${tmp_dir}/scripts/install-newsletter-rspamd.sh"
  fetch_asset \
    "scripts/rspamd/moolias_newsletter.lua" \
    "${tmp_dir}/scripts/rspamd/moolias_newsletter.lua"

  bash -n "${tmp_dir}/scripts/install-newsletter-agent.sh" \
    || fail "downloaded Newsletter Agent installer failed syntax validation."
  bash -n "${tmp_dir}/scripts/install-newsletter-rspamd.sh" \
    || fail "downloaded Rspamd installer failed syntax validation."

  echo "Installing Newsletter Management from ${install_ref}..."
  bash "${tmp_dir}/scripts/install-newsletter-agent.sh" "$@"
}

main "$@"
