#!/usr/bin/env bash
set -euo pipefail

# Parse the complete installer before starting child processes. This keeps
# `curl | sudo bash` safe from child processes consuming unparsed script input.
main() {
REPOSITORY="${MOOLIAS_REPOSITORY:-vain90/Moolias}"
MAILCOW_DIR="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
INSTALL_DIR="${MOOLIAS_INSTALL_DIR:-/opt/moolias}"
SOURCE_DIR="${MOOLIAS_SOURCE_DIR:-}"
INSTALL_REF="${MOOLIAS_INSTALL_REF:-}"
IMAGE_REPOSITORY="${MOOLIAS_IMAGE_REPOSITORY:-ghcr.io/vain90/moolias}"
IMAGE_TAG="${MOOLIAS_IMAGE_TAG:-latest}"
TLS_MODE="${MOOLIAS_TLS_MODE:-ask}"
INSTALL_SENDER_PROTECTION="${MOOLIAS_INSTALL_SENDER_PROTECTION:-ask}"
NONINTERACTIVE="${MOOLIAS_NONINTERACTIVE:-false}"
SKIP_PULL="${MOOLIAS_SKIP_PULL:-false}"

MAILCOW_CONF="${MAILCOW_DIR}/mailcow.conf"
NGINX_CUSTOM="${MAILCOW_DIR}/data/conf/nginx/moolias.conf"
INSTALL_MARKER="${INSTALL_DIR}/.moolias-mailcow-install"
RAW_BASE_URL="https://raw.githubusercontent.com/${REPOSITORY}"
LATEST_RELEASE_URL="https://github.com/${REPOSITORY}/releases/latest"
NGINX_MARKER="# Managed by Moolias Mailcow installer."

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'Moolias installer: %s\n' "$*" >&2
  exit 1
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

is_true() {
  case "${1,,}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

strip_quotes() {
  local value="$1"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
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
  strip_quotes "$value"
}

set_key_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp

  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] \
    || die "${key} must be a single-line value."

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

backup_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    cp -a "$path" "${path}.before-moolias-${stamp}.bak"
  fi
}

get_latest_release_tag() {
  local final_url tag
  final_url="$(
    curl --proto '=https' --tlsv1.2 -fsSL \
      -o /dev/null \
      -w '%{url_effective}' \
      "$LATEST_RELEASE_URL"
  )" || die "could not determine the latest stable Moolias release."

  tag="${final_url##*/}"
  [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([+][0-9A-Za-z.-]+)?$ ]] \
    || die "unexpected latest release tag: ${tag}"
  printf '%s\n' "$tag"
}

fetch_asset() {
  local path="$1"
  local destination="$2"

  if [[ -n "$SOURCE_DIR" ]]; then
    [[ -f "${SOURCE_DIR}/${path}" ]] \
      || die "local source file is missing: ${SOURCE_DIR}/${path}"
    cp -a "${SOURCE_DIR}/${path}" "$destination"
    return 0
  fi

  curl --proto '=https' --tlsv1.2 -fsSL \
    "${RAW_BASE_URL}/${INSTALL_REF}/${path}" \
    -o "$destination" \
    || die "could not download ${path} from ${INSTALL_REF}."
}

mailcow_compose() {
  (
    cd "$MAILCOW_DIR"
    docker compose "$@"
  )
}

open_tty() {
  if [[ -r /dev/tty && -w /dev/tty ]]; then
    exec 3<>/dev/tty
    return 0
  fi
  return 1
}

prompt_value() {
  local label="$1"
  local default_value="$2"
  local value=""

  [[ "$NONINTERACTIVE" != "true" ]] \
    || die "${label} is required in non-interactive mode."
  [[ "$tty_available" == true ]] \
    || die "interactive input is unavailable; use non-interactive environment variables."

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
  local current_value="$2"
  local value=""

  if [[ -n "$current_value" ]]; then
    printf '%s' "$current_value"
    return 0
  fi

  [[ "$NONINTERACTIVE" != "true" ]] \
    || die "${label} is required in non-interactive mode."
  [[ "$tty_available" == true ]] \
    || die "interactive input is unavailable; provide the required secret as an environment variable."

  printf '%s: ' "$label" >&3
  IFS= read -r -s value <&3
  printf '\n' >&3
  [[ -n "$value" ]] || die "${label} must not be empty."
  printf '%s' "$value"
}

prompt_yes_no() {
  local label="$1"
  local default_answer="$2"
  local answer=""

  if [[ "$NONINTERACTIVE" == "true" || "$tty_available" != true ]]; then
    [[ "$default_answer" == "yes" ]]
    return
  fi

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
    *) die "please answer yes or no." ;;
  esac
}

csv_contains() {
  local csv="$1"
  local needle="${2,,}"
  local item
  local -a items=()

  IFS=',' read -r -a items <<< "$csv"
  for item in "${items[@]}"; do
    item="${item//[[:space:]]/}"
    [[ "${item,,}" == "$needle" ]] && return 0
  done
  return 1
}

append_csv_value() {
  local csv="$1"
  local value="$2"

  if csv_contains "$csv" "$value"; then
    printf '%s' "$csv"
  elif [[ -z "${csv//[[:space:]]/}" ]]; then
    printf '%s' "$value"
  else
    printf '%s,%s' "$csv" "$value"
  fi
}

discover_mailcow_network() {
  local nginx_id network label
  nginx_id="$(mailcow_compose ps -q nginx-mailcow)"
  [[ -n "$nginx_id" ]] || die "nginx-mailcow is not running."

  while IFS= read -r network; do
    [[ -n "$network" ]] || continue
    label="$(docker network inspect \
      --format '{{index .Labels "com.docker.compose.network"}}' \
      "$network" 2>/dev/null || true)"
    if [[ "$label" == "mailcow-network" ]]; then
      printf '%s\n' "$network"
      return 0
    fi
  done < <(
    docker inspect \
      --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
      "$nginx_id"
  )

  die "could not identify Mailcow's Docker network from nginx-mailcow."
}

wait_for_moolias() {
  local container_id state
  for _ in $(seq 1 45); do
    container_id="$(docker compose ps -q moolias 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      state="$(docker inspect \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$container_id" 2>/dev/null || true)"
      case "$state" in
        healthy) return 0 ;;
        unhealthy|exited|dead) return 1 ;;
      esac
    fi
    sleep 2
  done
  return 1
}

write_nginx_config() {
  local destination="$1"
  local public_scheme="$2"
  local hostname="$3"
  local http_port="$4"
  local https_port="$5"
  local ipv6_enabled="$6"
  local proxy_protocol_enabled="$7"
  local listen_proxy=""
  local remote_addr='$remote_addr'
  local ipv6_http=""
  local ipv6_https=""
  local http_behavior=""

  if [[ "$proxy_protocol_enabled" == "true" ]]; then
    listen_proxy=" proxy_protocol"
    remote_addr='$proxy_protocol_addr'
  fi

  if [[ "$ipv6_enabled" == "true" ]]; then
    ipv6_http="    listen [::]:${http_port}${listen_proxy};"
    ipv6_https="    listen [::]:${https_port}${listen_proxy} ssl;"
  fi

  if [[ "$public_scheme" == "https" ]]; then
    http_behavior='        if ($moolias_forwarded_proto = http) { return 301 https://$host$request_uri; }'
  fi

  cat > "$destination" <<EOF
${NGINX_MARKER}

map \$http_x_forwarded_proto \$moolias_forwarded_proto {
    default \$http_x_forwarded_proto;
    ""      \$scheme;
}

server {
    listen ${http_port}${listen_proxy};
${ipv6_http}
    server_name ${hostname};
    root /web;

    location ^~ /.well-known/acme-challenge/ {
        allow all;
        default_type "text/plain";
    }

    location / {
${http_behavior}
        proxy_pass http://moolias-app:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP ${remote_addr};
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$moolias_forwarded_proto;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_redirect off;
    }
}

server {
    listen ${https_port}${listen_proxy} ssl;
${ipv6_https}
    http2 on;
    server_name ${hostname};

    ssl_certificate /etc/ssl/mail/cert.pem;
    ssl_certificate_key /etc/ssl/mail/key.pem;

    location / {
        proxy_pass http://moolias-app:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP ${remote_addr};
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_redirect off;
    }
}
EOF
}

if [[ "${EUID}" -ne 0 ]]; then
  die "run this installer as root, for example with curl ... | sudo bash."
fi

need_command awk
need_command curl
need_command docker
need_command grep
need_command mktemp
need_command sed

docker compose version >/dev/null 2>&1 \
  || die "Docker Compose v2 is required."

tty_available=false
if open_tty; then
  tty_available=true
fi

[[ -d "$MAILCOW_DIR" ]] || die "Mailcow directory not found: $MAILCOW_DIR"
[[ -f "${MAILCOW_DIR}/docker-compose.yml" ]] \
  || die "docker-compose.yml not found in $MAILCOW_DIR"
[[ -f "$MAILCOW_CONF" ]] || die "mailcow.conf not found in $MAILCOW_DIR"
[[ -d "${MAILCOW_DIR}/data/conf/nginx" ]] \
  || die "Mailcow nginx configuration directory is missing."

mailcow_compose config >/dev/null \
  || die "Mailcow Docker Compose configuration is invalid."

if [[ -z "$INSTALL_REF" ]]; then
  INSTALL_REF="$(get_latest_release_tag)"
fi

if [[ -z "$SOURCE_DIR" ]]; then
  [[ "$INSTALL_REF" =~ ^[A-Za-z0-9._/+:-]+$ ]] \
    || die "MOOLIAS_INSTALL_REF contains unsupported characters."
fi

[[ "$IMAGE_REPOSITORY" =~ ^[A-Za-z0-9._/:@-]+$ ]] \
  || die "MOOLIAS_IMAGE_REPOSITORY contains unsupported characters."
[[ "$IMAGE_TAG" =~ ^[A-Za-z0-9._+-]+$ ]] \
  || die "MOOLIAS_IMAGE_TAG contains unsupported characters."

stamp="$(date +%Y%m%d-%H%M%S)"

mailcow_hostname="$(read_key_value "$MAILCOW_CONF" MAILCOW_HOSTNAME || true)"
[[ -n "$mailcow_hostname" ]] || die "MAILCOW_HOSTNAME is missing from mailcow.conf."

existing_env="${INSTALL_DIR}/.env"
existing_base_url=""
existing_mailcow_url=""
existing_api_key=""
existing_oauth_id=""
existing_oauth_secret=""
existing_session_secret=""
existing_sender_protection=""
if [[ -f "$existing_env" ]]; then
  existing_base_url="$(read_key_value "$existing_env" MOOLIAS_BASE_URL || true)"
  existing_mailcow_url="$(read_key_value "$existing_env" MAILCOW_URL || true)"
  existing_api_key="$(read_key_value "$existing_env" MAILCOW_API_KEY || true)"
  existing_oauth_id="$(read_key_value "$existing_env" MAILCOW_OAUTH_CLIENT_ID || true)"
  existing_oauth_secret="$(read_key_value "$existing_env" MAILCOW_OAUTH_CLIENT_SECRET || true)"
  existing_session_secret="$(read_key_value "$existing_env" MOOLIAS_SESSION_SECRET || true)"
  existing_sender_protection="$(read_key_value "$existing_env" MOOLIAS_SENDER_PROTECTION || true)"
fi

domain_part="${mailcow_hostname#*.}"
if [[ "$domain_part" == "$mailcow_hostname" ]]; then
  default_moolias_hostname="moolias.${mailcow_hostname}"
else
  default_moolias_hostname="moolias.${domain_part}"
fi

default_base_url="https://${default_moolias_hostname}"
base_url="${MOOLIAS_BASE_URL:-${existing_base_url:-}}"
if [[ -z "$base_url" ]]; then
  base_url="$(prompt_value "Public Moolias URL" "$default_base_url")"
fi
base_url="${base_url%/}"

if [[ "$base_url" =~ ^(https?)://([A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?)(:([0-9]{1,5}))?$ ]]; then
  public_scheme="${BASH_REMATCH[1]}"
  moolias_hostname="${BASH_REMATCH[2],,}"
  public_port="${BASH_REMATCH[5]:-}"
else
  die "MOOLIAS_BASE_URL must be an http(s) origin without a path, for example https://moolias.example.org."
fi

if [[ -n "$public_port" ]] && (( public_port < 1 || public_port > 65535 )); then
  die "MOOLIAS_BASE_URL contains an invalid port."
fi

[[ "$moolias_hostname" != "${mailcow_hostname,,}" ]] \
  || die "Moolias needs its own hostname; do not reuse MAILCOW_HOSTNAME."

additional_server_names="$(read_key_value "$MAILCOW_CONF" ADDITIONAL_SERVER_NAMES || true)"
if csv_contains "$additional_server_names" "$moolias_hostname"; then
  die "${moolias_hostname} is already in ADDITIONAL_SERVER_NAMES. Remove it there so the dedicated Moolias nginx server can own that hostname."
fi

mailcow_url="${MAILCOW_URL:-${existing_mailcow_url:-https://${mailcow_hostname}}}"
mailcow_url="${mailcow_url%/}"
[[ "$mailcow_url" =~ ^https?://[^/]+$ ]] \
  || die "MAILCOW_URL must be an http(s) origin without a path."

api_key="${MAILCOW_API_KEY:-$existing_api_key}"
if [[ -z "$api_key" ]]; then
  api_key="$(prompt_secret "Mailcow read/write API key" "")"
fi

oauth_id="${MAILCOW_OAUTH_CLIENT_ID:-$existing_oauth_id}"
if [[ -z "$oauth_id" ]]; then
  oauth_id="$(prompt_value "Mailcow OAuth client ID" "")"
fi
[[ -n "$oauth_id" ]] || die "Mailcow OAuth client ID must not be empty."

oauth_secret="${MAILCOW_OAUTH_CLIENT_SECRET:-$existing_oauth_secret}"
if [[ -z "$oauth_secret" ]]; then
  oauth_secret="$(prompt_secret "Mailcow OAuth client secret" "")"
fi

session_secret="${MOOLIAS_SESSION_SECRET:-$existing_session_secret}"
if [[ -z "$session_secret" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    session_secret="$(openssl rand -hex 32)"
  else
    session_secret="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  fi
fi
[[ ${#session_secret} -ge 32 ]] \
  || die "could not create a sufficiently long Moolias session secret."

mailcow_network="$(discover_mailcow_network)"
[[ "$mailcow_network" =~ ^[A-Za-z0-9_.-]+$ ]] \
  || die "detected Mailcow Docker network contains unsupported characters: $mailcow_network"

http_port="$(read_key_value "$MAILCOW_CONF" HTTP_PORT || true)"
http_port="${http_port:-80}"
https_port="$(read_key_value "$MAILCOW_CONF" HTTPS_PORT || true)"
https_port="${https_port:-443}"
[[ "$http_port" =~ ^[0-9]+$ && "$https_port" =~ ^[0-9]+$ ]] \
  || die "Mailcow HTTP_PORT and HTTPS_PORT must be numeric."

enable_ipv6="$(read_key_value "$MAILCOW_CONF" ENABLE_IPV6 || true)"
if [[ "${enable_ipv6,,}" == "false" ]]; then
  ipv6_enabled=false
else
  ipv6_enabled=true
fi

nginx_proxy_protocol="$(read_key_value "$MAILCOW_CONF" NGINX_USE_PROXY_PROTOCOL || true)"
if is_true "${nginx_proxy_protocol:-n}"; then
  proxy_protocol_enabled=true
else
  proxy_protocol_enabled=false
fi

skip_le="$(read_key_value "$MAILCOW_CONF" SKIP_LETS_ENCRYPT || true)"
only_mailcow_hostname="$(read_key_value "$MAILCOW_CONF" ONLY_MAILCOW_HOSTNAME || true)"

if [[ "$public_scheme" == "http" ]]; then
  TLS_MODE="none"
elif [[ "$TLS_MODE" == "ask" ]]; then
  if is_true "${skip_le:-n}"; then
    TLS_MODE="external"
    log "Mailcow ACME is disabled; Moolias will not change Mailcow certificate settings."
  elif [[ "$NONINTERACTIVE" == "true" ]]; then
    die "set MOOLIAS_TLS_MODE=mailcow-acme or MOOLIAS_TLS_MODE=external in non-interactive HTTPS installs."
  elif prompt_yes_no "Add ${moolias_hostname} to Mailcow ACME (ADDITIONAL_SAN)?" "yes"; then
    TLS_MODE="mailcow-acme"
  else
    TLS_MODE="external"
  fi
fi

case "$TLS_MODE" in
  mailcow-acme)
    is_true "${skip_le:-n}" \
      && die "Mailcow ACME is disabled (SKIP_LETS_ENCRYPT); use MOOLIAS_TLS_MODE=external."
    is_true "${only_mailcow_hostname:-n}" \
      && die "ONLY_MAILCOW_HOSTNAME is enabled; Mailcow ACME will ignore ADDITIONAL_SAN. Use external TLS or change that Mailcow setting manually."
    ;;
  external|none)
    ;;
  *)
    die "MOOLIAS_TLS_MODE must be ask, mailcow-acme, external or none."
    ;;
esac

if [[ -d "$INSTALL_DIR" && ! -e "$INSTALL_MARKER" ]]; then
  if [[ -e "${INSTALL_DIR}/compose.yml" || -e "${INSTALL_DIR}/.env" ]]; then
    die "${INSTALL_DIR} already contains an unmanaged installation. Move it away or choose MOOLIAS_INSTALL_DIR."
  fi
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fetch_asset "compose.mailcow.yml" "${tmp_dir}/compose.yml"
fetch_asset ".env.example" "${tmp_dir}/env.example"
fetch_asset "update.sh" "${tmp_dir}/update.sh"
bash -n "${tmp_dir}/update.sh" \
  || die "downloaded update.sh failed syntax validation."

install -d -m 0755 "$INSTALL_DIR"

if [[ -f "${INSTALL_DIR}/compose.yml" ]]; then
  backup_file "${INSTALL_DIR}/compose.yml"
fi
install -m 0644 "${tmp_dir}/compose.yml" "${INSTALL_DIR}/compose.yml"

if [[ -f "${INSTALL_DIR}/update.sh" ]]; then
  backup_file "${INSTALL_DIR}/update.sh"
fi
install -m 0755 "${tmp_dir}/update.sh" "${INSTALL_DIR}/update.sh"

if [[ -f "${INSTALL_DIR}/.env" ]]; then
  backup_file "${INSTALL_DIR}/.env"
else
  install -m 0600 "${tmp_dir}/env.example" "${INSTALL_DIR}/.env"
fi

env_file="${INSTALL_DIR}/.env"
chmod 0600 "$env_file"

set_key_value "$env_file" MOOLIAS_BASE_URL "$base_url"
set_key_value "$env_file" MOOLIAS_SESSION_SECRET "$session_secret"
if [[ "$public_scheme" == "https" ]]; then
  set_key_value "$env_file" MOOLIAS_COOKIE_SECURE true
else
  set_key_value "$env_file" MOOLIAS_COOKIE_SECURE false
fi
set_key_value "$env_file" MOOLIAS_TRUSTED_HOSTS "$moolias_hostname"
set_key_value "$env_file" MAILCOW_URL "$mailcow_url"
set_key_value "$env_file" MAILCOW_API_KEY "$api_key"
set_key_value "$env_file" MAILCOW_OAUTH_CLIENT_ID "$oauth_id"
set_key_value "$env_file" MAILCOW_OAUTH_CLIENT_SECRET "$oauth_secret"
set_key_value "$env_file" MAILCOW_DOCKER_NETWORK "$mailcow_network"
set_key_value "$env_file" MOOLIAS_IMAGE "$IMAGE_REPOSITORY"
set_key_value "$env_file" MOOLIAS_TAG "$IMAGE_TAG"

cat > "$INSTALL_MARKER" <<EOF
managed_by=Moolias Mailcow installer
installed_ref=${INSTALL_REF}
mailcow_dir=${MAILCOW_DIR}
EOF
chmod 0644 "$INSTALL_MARKER"

if [[ "$TLS_MODE" == "mailcow-acme" ]]; then
  additional_san="$(read_key_value "$MAILCOW_CONF" ADDITIONAL_SAN || true)"
  updated_san="$(append_csv_value "$additional_san" "$moolias_hostname")"
  if [[ "$updated_san" != "$additional_san" ]]; then
    backup_file "$MAILCOW_CONF"
    set_key_value "$MAILCOW_CONF" ADDITIONAL_SAN "$updated_san"
    acme_changed=true
  else
    acme_changed=false
  fi
else
  acme_changed=false
fi

cd "$INSTALL_DIR"
docker compose config >/dev/null \
  || die "generated Moolias Docker Compose configuration is invalid."

if ! is_true "$SKIP_PULL"; then
  docker compose pull moolias
fi

docker compose up -d moolias

if ! wait_for_moolias; then
  docker compose logs --tail=100 moolias >&2 || true
  die "Moolias did not become healthy."
fi

nginx_tmp="${tmp_dir}/moolias.conf"
write_nginx_config \
  "$nginx_tmp" \
  "$public_scheme" \
  "$moolias_hostname" \
  "$http_port" \
  "$https_port" \
  "$ipv6_enabled" \
  "$proxy_protocol_enabled"

if [[ -e "$NGINX_CUSTOM" ]] && ! grep -Fq "$NGINX_MARKER" "$NGINX_CUSTOM"; then
  die "$NGINX_CUSTOM already exists but is not managed by Moolias."
fi

backup_file "$NGINX_CUSTOM"
install -m 0644 "$nginx_tmp" "$NGINX_CUSTOM"

if ! mailcow_compose exec -T nginx-mailcow nginx -t; then
  die "Mailcow nginx rejected the Moolias proxy configuration. A backup is available next to ${NGINX_CUSTOM}."
fi
mailcow_compose exec -T nginx-mailcow nginx -s reload

if [[ "$acme_changed" == "true" ]]; then
  log "Recreating acme-mailcow so it can request a certificate containing ${moolias_hostname}..."
  mailcow_compose up -d --no-deps --force-recreate acme-mailcow
fi

sender_protection_enabled=false
if is_true "${existing_sender_protection:-false}"; then
  sender_protection_enabled=true
elif [[ "$INSTALL_SENDER_PROTECTION" == "ask" ]]; then
  if prompt_yes_no "Install optional primary sender protection now?" "no"; then
    INSTALL_SENDER_PROTECTION="yes"
  else
    INSTALL_SENDER_PROTECTION="no"
  fi
fi

case "${INSTALL_SENDER_PROTECTION,,}" in
  yes|y|true|1)
    agent_installer="${tmp_dir}/install-mailcow-agent.sh"
    fetch_asset "scripts/install-mailcow-agent.sh" "$agent_installer"
    bash -n "$agent_installer" \
      || die "downloaded Mailcow Agent installer failed syntax validation."

    if [[ "$tty_available" == "true" ]]; then
      MAILCOW_DIR="$MAILCOW_DIR" \
      MOOLIAS_AGENT_IMAGE="${IMAGE_REPOSITORY}:${IMAGE_TAG}" \
      bash "$agent_installer" <&3
    else
      MAILCOW_DIR="$MAILCOW_DIR" \
      MOOLIAS_AGENT_IMAGE="${IMAGE_REPOSITORY}:${IMAGE_TAG}" \
      MOOLIAS_IMPORT_EXISTING_SENDER_RULES=no \
      bash "$agent_installer"
    fi

    agent_env="${MAILCOW_DIR}/data/conf/moolias-sender-agent/agent.env"
    agent_secret="$(read_key_value "$agent_env" MOOLIAS_AGENT_SECRET || true)"
    [[ -n "$agent_secret" ]] || die "Mailcow Agent installed but its secret could not be read."

    set_key_value "$env_file" MOOLIAS_SENDER_PROTECTION true
    set_key_value "$env_file" MOOLIAS_SENDER_AGENT_SECRET "$agent_secret"

    cd "$INSTALL_DIR"
    docker compose up -d --force-recreate moolias
    wait_for_moolias || die "Moolias did not become healthy after enabling sender protection."
    sender_protection_enabled=true
    ;;
  no|n|false|0)
    ;;
  *)
    die "MOOLIAS_INSTALL_SENDER_PROTECTION must be ask, yes or no."
    ;;
esac

container_id="$(docker compose ps -q moolias)"
installed_version="$(docker inspect \
  --format '{{index .Config.Labels "org.opencontainers.image.version"}}' \
  "$container_id" 2>/dev/null || true)"

cat <<EOF

============================================================
Moolias installed successfully
============================================================

URL:
  ${base_url}

Installation:
  ${INSTALL_DIR}

Mailcow:
  ${MAILCOW_DIR}

Docker network:
  ${mailcow_network}

OAuth redirect URI:
  ${base_url}/oauth/callback

Image:
  ${IMAGE_REPOSITORY}:${IMAGE_TAG}

Version:
  ${installed_version:-unknown}

Sender protection:
  $([[ "$sender_protection_enabled" == "true" ]] && printf enabled || printf disabled)

Update later with:
  cd ${INSTALL_DIR}
  ./update.sh

EOF

if [[ "$TLS_MODE" == "mailcow-acme" ]]; then
  cat <<EOF
TLS:
  ${moolias_hostname} is present in Mailcow ADDITIONAL_SAN.
  Ensure public DNS points to this Mailcow host and allow acme-mailcow time
  to issue and activate the updated certificate.

EOF
elif [[ "$public_scheme" == "https" ]]; then
  cat <<EOF
TLS:
  Mailcow certificate settings were not changed.
  Ensure your existing certificate or external reverse proxy covers
  ${moolias_hostname}.

EOF
fi

cat <<EOF
The Moolias application has no published host port. Mailcow nginx reaches it
only through Mailcow's Docker network.

Secrets were written to ${env_file} with mode 0600 and were not printed.
============================================================
EOF
}

main "$@"
