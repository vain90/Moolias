#!/usr/bin/env bash
set -euo pipefail

MAILCOW_DIR="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RSPAMD_DIR="${MAILCOW_DIR}/data/conf/rspamd"
PLUGIN_DIR="${RSPAMD_DIR}/plugins.d"
RSPAMD_CONF="${RSPAMD_DIR}/rspamd.conf.local"
PLUGIN_TARGET="${PLUGIN_DIR}/moolias_newsletter.lua"
PLUGIN_SOURCE="${SCRIPT_DIR}/rspamd/moolias_newsletter.lua"
CONF_BEGIN="# BEGIN MOOLIAS NEWSLETTER RSPAMD"
CONF_END="# END MOOLIAS NEWSLETTER RSPAMD"

fail() {
  echo "Moolias Newsletter Rspamd installer: $*" >&2
  exit 1
}

strip_block() {
  local source="$1"
  local begin="$2"
  local end="$3"
  awk -v begin="$begin" -v end="$end" '
    index($0, begin) { skip = 1; next }
    index($0, end) { skip = 0; next }
    !skip { print }
  ' "$source"
}

[[ ${EUID} -eq 0 ]] || fail "run this installer as root."
command -v docker >/dev/null 2>&1 || fail "Docker is required."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
[[ -f "${MAILCOW_DIR}/docker-compose.yml" ]] || fail "Mailcow not found at ${MAILCOW_DIR}."
[[ -d "$RSPAMD_DIR" ]] || fail "Mailcow Rspamd configuration directory is missing."
[[ -f "$PLUGIN_SOURCE" ]] || fail "Rspamd detector source is missing at ${PLUGIN_SOURCE}."

install -d -m 0755 "$PLUGIN_DIR"
touch "$RSPAMD_CONF"

backup_dir="$(mktemp -d "${MAILCOW_DIR}/.moolias-newsletter-rspamd-backup.XXXXXX")"
had_plugin=false
had_conf=false
if [[ -f "$PLUGIN_TARGET" ]]; then
  cp -a "$PLUGIN_TARGET" "$backup_dir/plugin.lua"
  had_plugin=true
fi
if [[ -f "$RSPAMD_CONF" ]]; then
  cp -a "$RSPAMD_CONF" "$backup_dir/rspamd.conf.local"
  had_conf=true
fi

restore() {
  if [[ "$had_plugin" == true ]]; then
    cp -a "$backup_dir/plugin.lua" "$PLUGIN_TARGET"
  else
    rm -f "$PLUGIN_TARGET"
  fi
  if [[ "$had_conf" == true ]]; then
    cp -a "$backup_dir/rspamd.conf.local" "$RSPAMD_CONF"
  fi
}

cleanup() {
  rm -rf "$backup_dir"
}
trap cleanup EXIT

install -m 0644 "$PLUGIN_SOURCE" "$PLUGIN_TARGET"

conf_new="$(mktemp "${RSPAMD_DIR}/.rspamd.conf.local.newsletter.XXXXXX")"
strip_block "$RSPAMD_CONF" "$CONF_BEGIN" "$CONF_END" > "$conf_new"
[[ ! -s "$conf_new" ]] || echo >> "$conf_new"
cat >> "$conf_new" <<EOF
$CONF_BEGIN
moolias_newsletter { }
$CONF_END
EOF
chmod --reference="$RSPAMD_CONF" "$conf_new" 2>/dev/null || chmod 0644 "$conf_new"
chown --reference="$RSPAMD_CONF" "$conf_new" 2>/dev/null || true
mv "$conf_new" "$RSPAMD_CONF"

cd "$MAILCOW_DIR"
if ! docker compose exec -T rspamd-mailcow rspamadm configtest >/dev/null; then
  restore
  fail "Rspamd rejected the Moolias newsletter detector configuration; previous files were restored."
fi

docker compose restart rspamd-mailcow

echo
echo "Moolias newsletter body detector installed successfully."
echo "Rspamd symbol: MOOLIAS_BODY_UNSUB"
