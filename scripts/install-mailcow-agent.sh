#!/usr/bin/env bash
set -euo pipefail

# Parse the complete installer before executing Docker commands. When this script
# is supplied through stdin (for example, curl | bash), child processes must not
# be able to consume installer bytes that Bash has not parsed yet.
main() {
MAILCOW_DIR="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
MOOLIAS_AGENT_IMAGE="${MOOLIAS_AGENT_IMAGE:-ghcr.io/vain90/moolias:edge}"
MOOLIAS_AGENT_COOLDOWN_SECONDS="${MOOLIAS_AGENT_COOLDOWN_SECONDS:-10}"
MOOLIAS_IMPORT_EXISTING_SENDER_RULES="${MOOLIAS_IMPORT_EXISTING_SENDER_RULES:-ask}"

POSTFIX_DIR="${MAILCOW_DIR}/data/conf/postfix"
POSTFIX_HOOK_DIR="${MAILCOW_DIR}/data/hooks/postfix"
POSTFIX_HOOK="${POSTFIX_HOOK_DIR}/moolias-sender-protection.sh"
RSPAMD_DIR="${MAILCOW_DIR}/data/conf/rspamd"
RSPAMD_PLUGIN_DIR="${RSPAMD_DIR}/plugins.d"
RSPAMD_CONF="${RSPAMD_DIR}/rspamd.conf.local"
RSPAMD_CUSTOM_DIR="${RSPAMD_DIR}/custom/moolias-sender-agent"
RSPAMD_BYPASS_MAP="${RSPAMD_CUSTOM_DIR}/moolias_firstmail_recipients.map"
RSPAMD_PLUGIN="${RSPAMD_PLUGIN_DIR}/moolias_firstmail.lua"
RSPAMD_HOOK_DIR="${MAILCOW_DIR}/data/hooks/rspamd"
RSPAMD_HOOK="${RSPAMD_HOOK_DIR}/moolias-firstmail.sh"
NGINX_DIR="${MAILCOW_DIR}/data/conf/nginx"
AGENT_DIR="${MAILCOW_DIR}/data/conf/moolias-sender-agent"
STATE_DIR="${AGENT_DIR}/state"
POLICY_DIR="${POSTFIX_DIR}/moolias-sender-agent"
EXTRA_CF="${POSTFIX_DIR}/extra.cf"
LEGACY_PCRE="${POSTFIX_DIR}/blocked_sender_login.pcre"
NGINX_CUSTOM="${NGINX_DIR}/site.moolias-sender-agent.custom"
OVERRIDE_FILE="${MAILCOW_DIR}/docker-compose.override.yml"
AGENT_ENV="${AGENT_DIR}/agent.env"

PCRE_MAP="pcre:/opt/postfix/conf/moolias-sender-agent/blocked_sender_login.pcre"
LEGACY_MAP="pcre:/opt/postfix/conf/blocked_sender_login.pcre"
OLD_PCRE_MAP="pcre:/opt/moolias-sender-agent/blocked_sender_login.pcre"
SQL_SENDER_MAP="proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf"
BEGIN_MARKER="# BEGIN MOOLIAS SENDER PROTECTION"
END_MARKER="# END MOOLIAS SENDER PROTECTION"
COMPOSE_BEGIN="# BEGIN MOOLIAS SENDER AGENT"
COMPOSE_END="# END MOOLIAS SENDER AGENT"
RSPAMD_BEGIN="# BEGIN MOOLIAS FIRST MAIL DELIVERY"
RSPAMD_END="# END MOOLIAS FIRST MAIL DELIVERY"
HOOK_MARKER="# Managed by Moolias Sender Protection."
RSPAMD_HOOK_MARKER="# Managed by Moolias First Mail Delivery."
RSPAMD_PLUGIN_MARKER="Managed by Moolias Mailcow Agent installer."
NGINX_MARKER="# Managed by Moolias Sender Protection."

die() {
  echo "Moolias Mailcow Agent installer: $*" >&2
  exit 1
}

backup_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    cp -a "$path" "${path}.before-moolias-agent-${stamp}.bak"
  fi
}

strip_managed_block() {
  local source="$1"
  local begin="$2"
  local end="$3"
  awk -v begin="$begin" -v end="$end" '
    index($0, begin) { skip = 1; next }
    index($0, end) { skip = 0; next }
    !skip { print }
  ' "$source"
}

if [[ "${EUID}" -ne 0 ]]; then
  die "run this installer as root, for example with sudo."
fi

command -v docker >/dev/null 2>&1 || die "Docker is required."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."

[[ -d "$MAILCOW_DIR" ]] || die "Mailcow directory not found: $MAILCOW_DIR"
[[ -f "${MAILCOW_DIR}/docker-compose.yml" ]] || \
  die "docker-compose.yml not found in $MAILCOW_DIR"
[[ -d "$POSTFIX_DIR" ]] || die "Mailcow Postfix configuration directory is missing."
[[ -d "$RSPAMD_DIR" ]] || die "Mailcow Rspamd configuration directory is missing."
[[ -d "$NGINX_DIR" ]] || die "Mailcow nginx configuration directory is missing."

if ! [[ "$MOOLIAS_AGENT_COOLDOWN_SECONDS" =~ ^[0-9]+$ ]] \
  || (( MOOLIAS_AGENT_COOLDOWN_SECONDS < 1 || MOOLIAS_AGENT_COOLDOWN_SECONDS > 300 )); then
  die "MOOLIAS_AGENT_COOLDOWN_SECONDS must be an integer between 1 and 300."
fi

case "${MOOLIAS_IMPORT_EXISTING_SENDER_RULES,,}" in
  ask|yes|no) ;;
  *) die "MOOLIAS_IMPORT_EXISTING_SENDER_RULES must be ask, yes or no." ;;
esac

if ! [[ "$MOOLIAS_AGENT_IMAGE" =~ ^[A-Za-z0-9._/:@-]+$ ]]; then
  die "MOOLIAS_AGENT_IMAGE contains unsupported characters."
fi

stamp="$(date +%Y%m%d-%H%M%S)"
touch "$EXTRA_CF"

# Preserve whether a previous installer-owned sender map still referenced the
# administrator's legacy PCRE. This makes reruns safe after a partial install.
managed_block_had_legacy=false
if awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" -v legacy="$LEGACY_MAP" '
  index($0, begin) { managed = 1; next }
  index($0, end) { managed = 0; next }
  managed && index($0, legacy) { found = 1 }
  END { exit(found ? 0 : 1) }
' "$EXTRA_CF"; then
  managed_block_had_legacy=true
fi

# Remove only the installer-owned sender-map block before inspecting any
# administrator configuration around it.
extra_without_moolias="$(mktemp "${POSTFIX_DIR}/.extra.cf.moolias.XXXXXX")"
strip_managed_block "$EXTRA_CF" "$BEGIN_MARKER" "$END_MARKER" > "$extra_without_moolias"

sender_assignment="$(
  awk '
    /^[[:space:]]*smtpd_sender_login_maps[[:space:]]*=/ {
      capture = 1
      print
      next
    }
    capture && /^[[:space:]]+/ {
      print
      next
    }
    capture { exit }
  ' "$extra_without_moolias"
)"

legacy_was_active="$managed_block_had_legacy"
if [[ -n "$sender_assignment" ]]; then
  normalized_assignment="$(printf '%s' "$sender_assignment" | tr -d '[:space:]')"
  expected_legacy="smtpd_sender_login_maps=${LEGACY_MAP},${SQL_SENDER_MAP}"
  expected_current="smtpd_sender_login_maps=${PCRE_MAP},${SQL_SENDER_MAP}"
  expected_old="smtpd_sender_login_maps=${OLD_PCRE_MAP},${SQL_SENDER_MAP}"
  expected_both="smtpd_sender_login_maps=${LEGACY_MAP},${PCRE_MAP},${SQL_SENDER_MAP}"

  case "$normalized_assignment" in
    "$expected_legacy")
      legacy_was_active=true
      ;;
    "$expected_current"|"$expected_old")
      ;;
    "$expected_both")
      legacy_was_active=true
      ;;
    *)
      rm -f "$extra_without_moolias"
      die "extra.cf contains a custom smtpd_sender_login_maps policy that cannot be merged safely."
      ;;
  esac
fi

# Remove the compatible old assignment. It is replaced below with the complete
# ordered map list, while all unrelated extra.cf settings remain untouched.
extra_base="$(mktemp "${POSTFIX_DIR}/.extra.cf.base.XXXXXX")"
awk '
  /^[[:space:]]*smtpd_sender_login_maps[[:space:]]*=/ {
    skip = 1
    next
  }
  skip && /^[[:space:]]+/ { next }
  skip { skip = 0 }
  { print }
' "$extra_without_moolias" > "$extra_base"
rm -f "$extra_without_moolias"

install -d -m 0755 "$AGENT_DIR"
install -d -m 0755 "$POSTFIX_HOOK_DIR"
install -d -m 0755 "$RSPAMD_PLUGIN_DIR"
install -d -m 0755 "$RSPAMD_HOOK_DIR"
install -d -m 0700 -o 10001 -g 10001 "$STATE_DIR"
install -d -m 0755 -o 10001 -g 10001 "$POLICY_DIR"
install -d -m 0755 -o 10001 -g 10001 "$RSPAMD_CUSTOM_DIR"

if [[ ! -e "$RSPAMD_BYPASS_MAP" ]]; then
  cat > "$RSPAMD_BYPASS_MAP" <<'EOF'
# Managed by Moolias Mailcow Agent. Do not edit manually.
# Exact recipients temporarily exempt from first-delivery greylisting.
EOF
fi
chown 10001:10001 "$RSPAMD_BYPASS_MAP"
chmod 0644 "$RSPAMD_BYPASS_MAP"

# Detect simple exact-address rules in an already active manual PCRE map. The
# administrator can explicitly move these rules under Moolias management. Any
# rule that is not an unambiguous exact mailbox pattern is always left alone.
if [[ "$legacy_was_active" == true && -s "$LEGACY_PCRE" && ! -e "${STATE_DIR}/state.json" ]]; then
  exact_rules="$(mktemp)"
  active_rules="$(mktemp)"
  drop_lines="$(mktemp)"
  trap 'rm -f "${exact_rules:-}" "${active_rules:-}" "${drop_lines:-}" "${extra_base:-}"' EXIT

  grep -Ev '^[[:space:]]*(#|$)' "$LEGACY_PCRE" > "$active_rules" || true

  while IFS=$'\t' read -r line_number line_body; do
    parsed="$(
      printf '%s\n' "$line_body" \
        | sed -n 's#^[[:space:]]*/\^\(.*\)\$/[[:space:]]\+\([^[:space:]]\+\)[[:space:]]*$#\1\t\2#p'
    )"
    [[ -n "$parsed" ]] || continue

    pattern="${parsed%%$'\t'*}"
    owner="${parsed#*$'\t'}"
    [[ "$pattern" =~ ^([A-Za-z0-9_@-]|\\[.+-])+$ ]] || continue

    address="$(
      printf '%s\n' "$pattern" \
        | sed -E 's/\\([.+-])/\1/g' \
        | tr '[:upper:]' '[:lower:]'
    )"
    [[ "$address" =~ ^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+$ ]] || continue

    printf '%s\t%s\t%s\n' "$line_number" "$address" "$owner" >> "$exact_rules"
  done < <(nl -ba -w1 -s $'\t' "$LEGACY_PCRE")

  exact_count="$(wc -l < "$exact_rules" | tr -d ' ')"
  active_count="$(wc -l < "$active_rules" | tr -d ' ')"
  unknown_count=$((active_count - exact_count))

  if (( exact_count > 0 )); then
    echo
    echo "Existing exact sender rules were found in:"
    echo "  ${LEGACY_PCRE}"
    echo
    while IFS=$'\t' read -r _ address owner; do
      printf '  %-45s -> %s\n' "$address" "$owner"
    done < "$exact_rules"
    echo

    import_existing="${MOOLIAS_IMPORT_EXISTING_SENDER_RULES,,}"
    if [[ "$import_existing" == "ask" ]]; then
      if [[ -r /dev/tty && -w /dev/tty ]]; then
        printf 'Move these exact rules under Moolias management? [y/N] ' > /dev/tty
        read -r answer < /dev/tty || answer=""
        case "${answer,,}" in
          y|yes|j|ja) import_existing="yes" ;;
          *) import_existing="no" ;;
        esac
      else
        echo "No interactive terminal is available; keeping existing rules external."
        import_existing="no"
      fi
    fi

    blocked_addresses="$(mktemp)"
    external_addresses="$(mktemp)"
    trap 'rm -f "${exact_rules:-}" "${active_rules:-}" "${drop_lines:-}" "${blocked_addresses:-}" "${external_addresses:-}" "${extra_base:-}"' EXIT
    : > "$blocked_addresses"
    : > "$external_addresses"

    if [[ "$import_existing" == "yes" ]]; then
      backup_file "$LEGACY_PCRE"
      cut -f1 "$exact_rules" > "$drop_lines"
      cut -f2 "$exact_rules" | sort -u > "$blocked_addresses"

      legacy_new="$(mktemp "${POSTFIX_DIR}/.blocked_sender_login.pcre.XXXXXX")"
      awk 'NR==FNR { drop[$1] = 1; next } !drop[FNR] { print }' \
        "$drop_lines" "$LEGACY_PCRE" > "$legacy_new"
      chmod --reference="$LEGACY_PCRE" "$legacy_new" 2>/dev/null || chmod 0644 "$legacy_new"
      chown --reference="$LEGACY_PCRE" "$legacy_new" 2>/dev/null || true
      mv "$legacy_new" "$LEGACY_PCRE"
      echo "Moved ${exact_count} exact sender rule(s) under Moolias management."
    else
      cut -f2 "$exact_rules" | sort -u > "$external_addresses"
      echo "Kept ${exact_count} exact sender rule(s) under existing Postfix management."
    fi

    {
      printf '{"blocked":['
      first=true
      while IFS= read -r address; do
        [[ -n "$address" ]] || continue
        if [[ "$first" == true ]]; then first=false; else printf ','; fi
        printf '"%s"' "$address"
      done < "$blocked_addresses"
      printf '],"external_blocked":['
      first=true
      while IFS= read -r address; do
        [[ -n "$address" ]] || continue
        if [[ "$first" == true ]]; then first=false; else printf ','; fi
        printf '"%s"' "$address"
      done < "$external_addresses"
      printf '],"last_changed":{},"version":1}\n'
    } > "${STATE_DIR}/state.json"
    chown 10001:10001 "${STATE_DIR}/state.json"
    chmod 0600 "${STATE_DIR}/state.json"

    rm -f "$blocked_addresses" "$external_addresses"
  fi

  if (( unknown_count > 0 )); then
    echo "Keeping ${unknown_count} non-exact or custom PCRE rule(s) unchanged and outside Moolias management."
  fi

  rm -f "$exact_rules" "$active_rules" "$drop_lines"
  trap 'rm -f "${extra_base:-}"' EXIT
fi

legacy_active=false
if [[ "$legacy_was_active" == true && -f "$LEGACY_PCRE" ]] \
  && grep -Ev '^[[:space:]]*(#|$)' "$LEGACY_PCRE" >/dev/null 2>&1; then
  legacy_active=true
fi

if [[ -f "$AGENT_ENV" ]]; then
  secret="$(sed -n 's/^MOOLIAS_AGENT_SECRET=//p' "$AGENT_ENV" | head -n1)"
else
  secret=""
fi
if [[ -z "$secret" ]]; then
  secret="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
fi
[[ ${#secret} -ge 32 ]] || die "could not create a sufficiently long agent secret."

umask 077
cat > "$AGENT_ENV" <<EOF
MOOLIAS_AGENT_SECRET=${secret}
MOOLIAS_AGENT_STATE_DIR=/state
MOOLIAS_AGENT_POLICY_PATH=/postfix-policy/blocked_sender_login.pcre
MOOLIAS_AGENT_BYPASS_MAP_PATH=/rspamd-custom/moolias_firstmail_recipients.map
MOOLIAS_AGENT_COOLDOWN_SECONDS=${MOOLIAS_AGENT_COOLDOWN_SECONDS}
EOF
chmod 0600 "$AGENT_ENV"

backup_file "$POSTFIX_HOOK"
cat > "$POSTFIX_HOOK" <<EOF
#!/usr/bin/env bash
set -euo pipefail

${HOOK_MARKER}
# Postfix caches PCRE maps in smtpd workers. Limit only authenticated submission
# workers to one client connection so the next connection sees policy changes.
for service in smtps 10465 submission 10587 588; do
  if /usr/sbin/postconf -c /opt/postfix/conf -M "\${service}/inet" >/dev/null 2>&1; then
    /usr/sbin/postconf -c /opt/postfix/conf -P "\${service}/inet/max_use=1"
  fi
done
EOF
chmod 0755 "$POSTFIX_HOOK"

if [[ -f "$RSPAMD_HOOK" ]] && ! grep -Fq "$RSPAMD_HOOK_MARKER" "$RSPAMD_HOOK"; then
  rm -f "$extra_base"
  die "Rspamd hook path is already managed outside Moolias: $RSPAMD_HOOK"
fi
backup_file "$RSPAMD_HOOK"
cat > "$RSPAMD_HOOK" <<EOF
#!/usr/bin/env bash
set -euo pipefail

${RSPAMD_HOOK_MARKER}
install -d -m 0755 -o 10001 -g 10001 /etc/rspamd/custom/moolias-sender-agent
if [[ ! -e /etc/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map ]]; then
  touch /etc/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map
fi
chown 10001:10001 /etc/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map
chmod 0644 /etc/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map
EOF
chmod 0755 "$RSPAMD_HOOK"

if [[ -f "$RSPAMD_PLUGIN" ]] && ! grep -Fq "$RSPAMD_PLUGIN_MARKER" "$RSPAMD_PLUGIN"; then
  rm -f "$extra_base"
  die "Rspamd plugin path is already managed outside Moolias: $RSPAMD_PLUGIN"
fi
rspamd_plugin_existed=false
if [[ -f "$RSPAMD_PLUGIN" ]]; then
  rspamd_plugin_existed=true
  backup_file "$RSPAMD_PLUGIN"
fi
rspamd_conf_existed=false
if [[ -f "$RSPAMD_CONF" ]]; then
  rspamd_conf_existed=true
  backup_file "$RSPAMD_CONF"
else
  touch "$RSPAMD_CONF"
fi

cat > "$RSPAMD_PLUGIN" <<'EOF'
-- Managed by Moolias Mailcow Agent installer.
local section = rspamd_config:get_key("moolias_firstmail")
if type(section) ~= "table" or type(section.map) ~= "string" then
  return
end

local recipient_map = rspamd_config:add_hash_map(
  section.map,
  "Moolias first-delivery recipients"
)
if not recipient_map then
  return
end

local function skip_first_delivery_greylisting(task)
  local recipients = task:get_recipients("smtp")
  if not recipients or #recipients ~= 1 then
    return
  end

  local recipient = recipients[1] and recipients[1]["addr"]
  if type(recipient) ~= "string" then
    return
  end

  if recipient_map:get_key(string.lower(recipient)) then
    task:disable_symbol("GREYLIST_CHECK")
    task:disable_symbol("GREYLIST_SAVE")
  end
end

rspamd_config:register_pre_filter(skip_first_delivery_greylisting, -100)
EOF
chmod 0644 "$RSPAMD_PLUGIN"

rspamd_conf_new="$(mktemp "${RSPAMD_DIR}/.rspamd.conf.local.moolias.XXXXXX")"
strip_managed_block "$RSPAMD_CONF" "$RSPAMD_BEGIN" "$RSPAMD_END" > "$rspamd_conf_new"
[[ ! -s "$rspamd_conf_new" ]] || echo >> "$rspamd_conf_new"
cat >> "$rspamd_conf_new" <<EOF
${RSPAMD_BEGIN}
moolias_firstmail {
  map = "file:///etc/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map";
}
${RSPAMD_END}
EOF
chmod --reference="$RSPAMD_CONF" "$rspamd_conf_new" 2>/dev/null || chmod 0644 "$rspamd_conf_new"
chown --reference="$RSPAMD_CONF" "$rspamd_conf_new" 2>/dev/null || true
mv "$rspamd_conf_new" "$RSPAMD_CONF"

# The Compose override is needed only to define the small agent sidecar. Postfix
# and Rspamd already see their respective Mailcow configuration directories.
compose_base="$(mktemp "${MAILCOW_DIR}/.docker-compose.override.XXXXXX")"
if [[ -f "$OVERRIDE_FILE" ]]; then
  strip_managed_block "$OVERRIDE_FILE" "$COMPOSE_BEGIN" "$COMPOSE_END" > "$compose_base"
else
  : > "$compose_base"
fi

if grep -Eq '^[[:space:]]+moolias-sender-agent:[[:space:]]*$' "$compose_base"; then
  rm -f "$compose_base" "$extra_base"
  die "docker-compose.override.yml already defines moolias-sender-agent outside the managed block."
fi

# Match the indentation already used for service names in an existing override.
# YAML permits more than two spaces, but sibling service keys must stay at the
# same indentation level. Default to two spaces for a new or empty services map.
service_indent="$(
  awk '
    /^services:[[:space:]]*$/ { in_services = 1; next }
    in_services && /^[[:space:]]*($|#)/ { next }
    in_services && /^[^[:space:]]/ { exit }
    in_services {
      match($0, /^ +/)
      if (RLENGTH > 0) print RLENGTH
      exit
    }
  ' "$compose_base"
)"
service_indent="${service_indent:-2}"
[[ "$service_indent" =~ ^[0-9]+$ ]] || die "could not determine Compose service indentation."
(( service_indent >= 2 )) || die "Compose services must be indented by at least two spaces."

agent_compose="$(mktemp "${MAILCOW_DIR}/.moolias-agent-compose.XXXXXX")"
cat > "$agent_compose" <<EOF
  ${COMPOSE_BEGIN}
  moolias-sender-agent:
    image: ${MOOLIAS_AGENT_IMAGE}
    user: "10001:10001"
    restart: unless-stopped
    env_file:
      - ./data/conf/moolias-sender-agent/agent.env
    command:
      - uvicorn
      - moolias.mailcow_agent:create_agent_app
      - --factory
      - --host
      - 0.0.0.0
      - --port
      - "8081"
      - --proxy-headers
      - --forwarded-allow-ips
      - "*"
    volumes:
      - ./data/conf/moolias-sender-agent/state:/state
      - ./data/conf/postfix/moolias-sender-agent:/postfix-policy
      - ./data/conf/rspamd/custom/moolias-sender-agent:/rspamd-custom
    networks:
      - mailcow-network
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=3)
      interval: 30s
      timeout: 5s
      start_period: 5s
      retries: 3
  ${COMPOSE_END}
EOF

if (( service_indent > 2 )); then
  extra_indent="$(printf '%*s' "$((service_indent - 2))" '')"
  sed "s/^/${extra_indent}/" "$agent_compose" > "${agent_compose}.indented"
  mv "${agent_compose}.indented" "$agent_compose"
fi

compose_new="$(mktemp "${MAILCOW_DIR}/.docker-compose.override.new.XXXXXX")"
if grep -Eq '^services:[[:space:]]*$' "$compose_base"; then
  awk -v fragment="$agent_compose" '
    BEGIN {
      while ((getline line < fragment) > 0) {
        block = block line "\n"
      }
      close(fragment)
    }
    /^services:[[:space:]]*$/ && !inserted {
      print
      printf "%s", block
      inserted = 1
      next
    }
    { print }
  ' "$compose_base" > "$compose_new"
else
  cat "$compose_base" > "$compose_new"
  [[ ! -s "$compose_new" ]] || echo >> "$compose_new"
  echo "services:" >> "$compose_new"
  cat "$agent_compose" >> "$compose_new"
fi
rm -f "$agent_compose" "$compose_base"

backup_file "$OVERRIDE_FILE"
chmod 0644 "$compose_new"
mv "$compose_new" "$OVERRIDE_FILE"

backup_file "$EXTRA_CF"
extra_new="$(mktemp "${POSTFIX_DIR}/.extra.cf.new.XXXXXX")"
cat "$extra_base" > "$extra_new"
rm -f "$extra_base"
if [[ -s "$extra_new" ]]; then
  echo >> "$extra_new"
fi
{
  echo "$BEGIN_MARKER"
  echo "# Moolias rules are evaluated before Mailcow's normal SQL sender ACL."
  echo "smtpd_sender_login_maps ="
  if [[ "$legacy_active" == true ]]; then
    echo "  ${LEGACY_MAP},"
  fi
  echo "  ${PCRE_MAP},"
  echo "  ${SQL_SENDER_MAP}"
  echo "$END_MARKER"
} >> "$extra_new"
chmod --reference="$EXTRA_CF" "$extra_new" 2>/dev/null || chmod 0644 "$extra_new"
chown --reference="$EXTRA_CF" "$extra_new" 2>/dev/null || true
mv "$extra_new" "$EXTRA_CF"
trap - EXIT

backup_file "$NGINX_CUSTOM"
cat > "$NGINX_CUSTOM" <<EOF
${NGINX_MARKER}
location ^~ /moolias-agent/ {
    proxy_pass http://moolias-sender-agent:8081/;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_connect_timeout 3s;
    proxy_send_timeout 10s;
    proxy_read_timeout 10s;
    client_max_body_size 4k;
}
EOF
chmod 0644 "$NGINX_CUSTOM"

cd "$MAILCOW_DIR"
docker compose config >/dev/null

if ! docker compose exec -T rspamd-mailcow rspamadm configtest >/dev/null; then
  if [[ "$rspamd_plugin_existed" == true ]]; then
    cp -a "${RSPAMD_PLUGIN}.before-moolias-agent-${stamp}.bak" "$RSPAMD_PLUGIN"
  else
    rm -f "$RSPAMD_PLUGIN"
  fi
  if [[ "$rspamd_conf_existed" == true ]]; then
    cp -a "${RSPAMD_CONF}.before-moolias-agent-${stamp}.bak" "$RSPAMD_CONF"
  else
    rm -f "$RSPAMD_CONF"
  fi
  die "Rspamd rejected the Moolias first-delivery configuration; previous Rspamd files were restored."
fi

if ! docker image inspect "$MOOLIAS_AGENT_IMAGE" >/dev/null 2>&1; then
  docker pull "$MOOLIAS_AGENT_IMAGE"
fi

docker compose up -d moolias-sender-agent

agent_ready=false
for _ in $(seq 1 30); do
  if docker compose exec -T moolias-sender-agent \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=2)" \
    >/dev/null 2>&1; then
    agent_ready=true
    break
  fi
  sleep 1
done
[[ "$agent_ready" == true ]] || die "agent container did not become healthy."

agent_id="$(docker compose ps -q moolias-sender-agent)"
[[ -n "$agent_id" ]] || die "could not resolve the running agent container."

agent_uid="$(docker compose exec -T moolias-sender-agent id -u | tr -d '[:space:]')"
agent_gid="$(docker compose exec -T moolias-sender-agent id -g | tr -d '[:space:]')"
[[ "$agent_uid" == "10001" && "$agent_gid" == "10001" ]] \
  || die "agent must run as uid/gid 10001:10001."

agent_readonly="$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$agent_id")"
[[ "$agent_readonly" == "true" ]] || die "agent root filesystem must be read-only."

agent_cap_drop="$(docker inspect -f '{{json .HostConfig.CapDrop}}' "$agent_id")"
grep -Fq '"ALL"' <<<"$agent_cap_drop" || die "agent must drop all Linux capabilities."

agent_security_opt="$(docker inspect -f '{{json .HostConfig.SecurityOpt}}' "$agent_id")"
grep -Fq 'no-new-privileges' <<<"$agent_security_opt" \
  || die "agent must enable no-new-privileges."

agent_ports="$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$agent_id")"
[[ "$agent_ports" == "{}" || "$agent_ports" == "null" ]] \
  || die "agent must not publish host ports."

agent_mounts="$(
  docker inspect -f '{{range .Mounts}}{{println .Destination .RW}}{{end}}' "$agent_id" \
    | sed '/^[[:space:]]*$/d' \
    | sort
)"
expected_agent_mounts="$(
  printf '%s\n' '/postfix-policy true' '/rspamd-custom true' '/state true' | sort
)"
[[ "$agent_mounts" == "$expected_agent_mounts" ]] \
  || die "agent has unexpected mounts; only its state and managed policy maps are allowed."

[[ -r "${POLICY_DIR}/blocked_sender_login.pcre" ]] \
  || die "agent did not render the Postfix policy file."
[[ -r "$RSPAMD_BYPASS_MAP" ]] \
  || die "agent did not render the first-delivery recipient map."

docker compose exec -T nginx-mailcow nginx -t
docker compose exec -T nginx-mailcow nginx -s reload

# extra.cf and the Postfix hook are consumed at container startup. No new
# Postfix mount is required, so a normal one-time restart is sufficient.
docker compose restart postfix-mailcow

postfix_ready=false
active_maps=""
for _ in $(seq 1 30); do
  active_maps="$(
    docker compose exec -T postfix-mailcow \
      postconf -c /opt/postfix/conf smtpd_sender_login_maps 2>/dev/null \
      || true
  )"
  if grep -Fq "$PCRE_MAP" <<<"$active_maps" \
    && grep -Fq "$SQL_SENDER_MAP" <<<"$active_maps"; then
    postfix_ready=true
    break
  fi
  sleep 1
done
[[ "$postfix_ready" == true ]] \
  || die "Postfix did not load the Moolias sender map within 30 seconds."

if [[ "$legacy_active" == true ]]; then
  grep -Fq "$LEGACY_MAP" <<<"$active_maps" \
    || die "Postfix did not retain the existing sender map."
fi

for service in smtps submission 588; do
  max_use="$(
    docker compose exec -T postfix-mailcow \
      postconf -c /opt/postfix/conf -P "${service}/inet/max_use" 2>/dev/null \
      || true
  )"
  grep -Eq '=[[:space:]]*1[[:space:]]*$' <<<"$max_use" \
    || die "Postfix service ${service}/inet did not load max_use=1 from the Moolias hook."
done

docker compose exec -T postfix-mailcow \
  test -r /opt/postfix/conf/moolias-sender-agent/blocked_sender_login.pcre \
  || die "Postfix cannot read the Moolias sender policy."

# Mailcow normalizes permissions below /etc/rspamd/custom on every Rspamd start.
# The installed hook runs afterwards and restores write access only for the
# dedicated Moolias recipient map used by the agent.
docker compose restart rspamd-mailcow
rspamd_ready=false
for _ in $(seq 1 30); do
  if docker compose exec -T rspamd-mailcow rspamadm configtest >/dev/null 2>&1; then
    rspamd_ready=true
    break
  fi
  sleep 1
done
[[ "$rspamd_ready" == true ]] || die "Rspamd did not become ready with the Moolias configuration."

docker compose exec -T rspamd-mailcow \
  test -r /etc/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map \
  || die "Rspamd cannot read the Moolias first-delivery recipient map."
docker compose exec -T moolias-sender-agent test -w /rspamd-custom \
  || die "Mailcow Agent cannot update the first-delivery recipient map after Rspamd restart."

cat <<EOF

============================================================
Moolias Mailcow Agent installed successfully
============================================================

NEXT STEP: Configure Moolias

Copy these values into the Moolias .env file:

------------------------------------------------------------
MOOLIAS_SENDER_PROTECTION=true
MOOLIAS_SENDER_AGENT_SECRET=${secret}
------------------------------------------------------------

Keep MOOLIAS_SENDER_AGENT_SECRET private. Do not share it or commit it to Git.

Moolias automatically uses MAILCOW_URL + /moolias-agent.
Only set MOOLIAS_SENDER_AGENT_URL when the agent is reachable at a different URL.

After updating the Moolias .env file, restart Moolias.

The agent uses Mailcow's existing Postfix and Rspamd configuration mounts. Existing
manual blocked_sender_login.pcre rules remain separate unless they were explicitly imported.

============================================================
EOF
}

main "$@"