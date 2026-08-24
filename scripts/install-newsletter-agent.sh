#!/usr/bin/env bash
set -euo pipefail

MAILCOW_DIR="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
MOOLIAS_DIR="${MOOLIAS_DIR:-/opt/moolias}"
MOOLIAS_AGENT_IMAGE="${MOOLIAS_AGENT_IMAGE:-ghcr.io/vain90/moolias:edge}"

DOVECOT_DIR="${MAILCOW_DIR}/data/conf/dovecot"
DOVECOT_EXTRA="${DOVECOT_DIR}/extra.conf"
NGINX_DIR="${MAILCOW_DIR}/data/conf/nginx"
NGINX_CUSTOM="${NGINX_DIR}/site.moolias-newsletter-agent.custom"
AGENT_DIR="${MAILCOW_DIR}/data/conf/moolias-newsletter-agent"
AGENT_ENV="${AGENT_DIR}/agent.env"
OVERRIDE_FILE="${MAILCOW_DIR}/docker-compose.override.yml"
MOOLIAS_ENV="${MOOLIAS_DIR}/.env"

DOVEADM_BEGIN="# BEGIN MOOLIAS NEWSLETTER DOVEADM"
DOVEADM_END="# END MOOLIAS NEWSLETTER DOVEADM"
COMPOSE_BEGIN="# BEGIN MOOLIAS NEWSLETTER AGENT"
COMPOSE_END="# END MOOLIAS NEWSLETTER AGENT"
NGINX_MARKER="# Managed by Moolias Newsletter Agent."

fail() {
  echo "Moolias Newsletter Agent installer: $*" >&2
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

set_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  if grep -qE "^${key}=" "$file"; then
    sed -i -E "s#^${key}=.*#${key}=${value}#" "$file"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$file"
  fi
}

[[ ${EUID} -eq 0 ]] || fail "run this installer as root."
command -v docker >/dev/null 2>&1 || fail "Docker is required."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
[[ -f "${MAILCOW_DIR}/docker-compose.yml" ]] || fail "Mailcow not found at ${MAILCOW_DIR}."
[[ -d "$DOVECOT_DIR" ]] || fail "Mailcow Dovecot configuration directory is missing."
[[ -d "$NGINX_DIR" ]] || fail "Mailcow nginx configuration directory is missing."
[[ -f "$MOOLIAS_ENV" ]] || fail "Moolias .env not found at ${MOOLIAS_ENV}."

install -d -m 0700 "$AGENT_DIR"
touch "$DOVECOT_EXTRA"

existing_agent_secret=""
existing_doveadm_password=""
if [[ -f "$AGENT_ENV" ]]; then
  existing_agent_secret="$(sed -n 's/^MOOLIAS_NEWSLETTER_AGENT_SECRET=//p' "$AGENT_ENV" | head -n1)"
  existing_doveadm_password="$(sed -n 's/^MOOLIAS_DOVEADM_PASSWORD=//p' "$AGENT_ENV" | head -n1)"
fi

agent_secret="${MOOLIAS_NEWSLETTER_AGENT_SECRET:-$existing_agent_secret}"
if [[ -z "$agent_secret" ]]; then
  agent_secret="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
fi
[[ ${#agent_secret} -ge 32 ]] || fail "newsletter agent secret must contain at least 32 characters."
[[ "$agent_secret" != *$'\n'* && "$agent_secret" != *$'\r'* ]] || fail "newsletter agent secret contains invalid characters."

external_doveadm_password="$(
  strip_block "$DOVECOT_EXTRA" "$DOVEADM_BEGIN" "$DOVEADM_END" \
    | sed -nE 's/^[[:space:]]*doveadm_password[[:space:]]*=[[:space:]]*([^[:space:]#]+).*$/\1/p' \
    | head -n1
)"
explicit_doveadm_password="${MOOLIAS_DOVEADM_PASSWORD:-}"
if [[ -n "$explicit_doveadm_password" ]]; then
  doveadm_password="$explicit_doveadm_password"
elif [[ -n "$external_doveadm_password" ]]; then
  # An administrator-owned Dovecot setting is authoritative. Reuse it instead of
  # silently replacing it with a stale password from an older agent environment.
  doveadm_password="$external_doveadm_password"
elif [[ -n "$existing_doveadm_password" ]]; then
  doveadm_password="$existing_doveadm_password"
else
  doveadm_password="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
fi
[[ "$doveadm_password" =~ ^[A-Za-z0-9._~:+-]{32,}$ ]] \
  || fail "doveadm password contains unsupported characters; use a simple 32+ character secret."

# If an administrator already configured doveadm_password, leave that setting in
# place and reuse it. Otherwise maintain one small installer-owned block.
if [[ -z "$external_doveadm_password" ]]; then
  dovecot_new="$(mktemp "${DOVECOT_DIR}/.extra.conf.newsletter.XXXXXX")"
  strip_block "$DOVECOT_EXTRA" "$DOVEADM_BEGIN" "$DOVEADM_END" > "$dovecot_new"
  [[ ! -s "$dovecot_new" ]] || echo >> "$dovecot_new"
  {
    echo "$DOVEADM_BEGIN"
    echo "doveadm_password = ${doveadm_password}"
    echo "$DOVEADM_END"
  } >> "$dovecot_new"
  chmod --reference="$DOVECOT_EXTRA" "$dovecot_new" 2>/dev/null || chmod 0644 "$dovecot_new"
  chown --reference="$DOVECOT_EXTRA" "$dovecot_new" 2>/dev/null || true
  mv "$dovecot_new" "$DOVECOT_EXTRA"
fi

umask 077
cat > "$AGENT_ENV" <<EOF
MOOLIAS_NEWSLETTER_AGENT_SECRET=${agent_secret}
MOOLIAS_DOVEADM_PASSWORD=${doveadm_password}
MOOLIAS_DOVEADM_HOST=dovecot-mailcow:12345
EOF
chmod 0600 "$AGENT_ENV"

compose_base="$(mktemp "${MAILCOW_DIR}/.docker-compose.override.newsletter.XXXXXX")"
if [[ -f "$OVERRIDE_FILE" ]]; then
  strip_block "$OVERRIDE_FILE" "$COMPOSE_BEGIN" "$COMPOSE_END" > "$compose_base"
else
  : > "$compose_base"
fi
if grep -Eq '^[[:space:]]+moolias-newsletter-agent:[[:space:]]*$' "$compose_base"; then
  rm -f "$compose_base"
  fail "docker-compose.override.yml already defines moolias-newsletter-agent outside the managed block."
fi

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
[[ "$service_indent" =~ ^[0-9]+$ ]] || fail "could not determine Compose indentation."
(( service_indent >= 2 )) || fail "Compose services must be indented by at least two spaces."

fragment="$(mktemp "${MAILCOW_DIR}/.moolias-newsletter-compose.XXXXXX")"
cat > "$fragment" <<EOF
  ${COMPOSE_BEGIN}
  moolias-newsletter-agent:
    image: ${MOOLIAS_AGENT_IMAGE}
    user: "10001:10001"
    restart: unless-stopped
    env_file:
      - ./data/conf/moolias-newsletter-agent/agent.env
    command:
      - uvicorn
      - moolias.newsletter_agent:create_newsletter_agent_app
      - --factory
      - --host
      - 0.0.0.0
      - --port
      - "8082"
      - --proxy-headers
      - --forwarded-allow-ips
      - "*"
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
          urllib.request.urlopen('http://127.0.0.1:8082/healthz', timeout=3)
      interval: 30s
      timeout: 5s
      start_period: 5s
      retries: 3
  ${COMPOSE_END}
EOF
if (( service_indent > 2 )); then
  indent="$(printf '%*s' "$((service_indent - 2))" '')"
  sed "s/^/${indent}/" "$fragment" > "${fragment}.indented"
  mv "${fragment}.indented" "$fragment"
fi

compose_new="$(mktemp "${MAILCOW_DIR}/.docker-compose.override.newsletter-new.XXXXXX")"
if grep -Eq '^services:[[:space:]]*$' "$compose_base"; then
  awk -v fragment="$fragment" '
    BEGIN {
      while ((getline line < fragment) > 0) block = block line "\n"
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
  cat "$fragment" >> "$compose_new"
fi
rm -f "$fragment" "$compose_base"
chmod 0644 "$compose_new"
mv "$compose_new" "$OVERRIDE_FILE"

cat > "$NGINX_CUSTOM" <<EOF
${NGINX_MARKER}
location ^~ /moolias-newsletter-agent/ {
    proxy_pass http://moolias-newsletter-agent:8082/;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_connect_timeout 3s;
    proxy_send_timeout 15s;
    proxy_read_timeout 15s;
    client_max_body_size 8k;
}
EOF
chmod 0644 "$NGINX_CUSTOM"

# Enable the feature in the Moolias application. The Dovecot password deliberately
# stays only on the Mailcow host and in the restricted agent container.
set_env_value "$MOOLIAS_ENV" "MOOLIAS_NEWSLETTER_MANAGEMENT" "true"
set_env_value "$MOOLIAS_ENV" "MOOLIAS_NEWSLETTER_AGENT_SECRET" "$agent_secret"
if ! grep -qE '^MOOLIAS_NEWSLETTER_DB_PATH=' "$MOOLIAS_ENV"; then
  set_env_value "$MOOLIAS_ENV" "MOOLIAS_NEWSLETTER_DB_PATH" "/data/moolias-newsletters.sqlite3"
fi

mailcow_internal_url="$(sed -n 's/^MAILCOW_INTERNAL_URL=//p' "$MOOLIAS_ENV" | tail -n1)"
mailcow_internal_url="${mailcow_internal_url%/}"
if [[ -n "$mailcow_internal_url" ]]; then
  set_env_value \
    "$MOOLIAS_ENV" \
    "MOOLIAS_NEWSLETTER_AGENT_URL" \
    "${mailcow_internal_url}/moolias-newsletter-agent"
fi

cd "$MAILCOW_DIR"
docker compose config >/dev/null
if ! docker image inspect "$MOOLIAS_AGENT_IMAGE" >/dev/null 2>&1; then
  docker pull "$MOOLIAS_AGENT_IMAGE"
fi

# Dovecot must reload the new remote doveadm password before the sidecar can use it.
docker compose restart dovecot-mailcow
docker compose up -d moolias-newsletter-agent

ready=false
for _ in $(seq 1 30); do
  if docker compose exec -T moolias-newsletter-agent \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/healthz', timeout=2)" \
    >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
[[ "$ready" == true ]] || fail "newsletter agent did not become healthy."

agent_id="$(docker compose ps -q moolias-newsletter-agent)"
[[ -n "$agent_id" ]] || fail "could not resolve the newsletter agent container."
[[ "$(docker compose exec -T moolias-newsletter-agent id -u | tr -d '[:space:]')" == "10001" ]] \
  || fail "newsletter agent must run as uid 10001."
[[ "$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$agent_id")" == "true" ]] \
  || fail "newsletter agent root filesystem must be read-only."
ports="$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$agent_id")"
[[ "$ports" == "{}" || "$ports" == "null" ]] || fail "newsletter agent must not publish host ports."
mounts="$(docker inspect -f '{{range .Mounts}}{{println .Destination}}{{end}}' "$agent_id" | sed '/^[[:space:]]*$/d')"
[[ -z "$mounts" ]] || fail "newsletter agent must not have host mounts."

docker compose exec -T nginx-mailcow nginx -t
docker compose exec -T nginx-mailcow nginx -s reload

echo
echo "Moolias Newsletter Agent installed successfully."
echo "Moolias configuration updated: ${MOOLIAS_ENV}"
echo "Restart or rebuild the Moolias application so the new settings and image are active."
