# Install Moolias on the Mailcow host

Running Moolias on the same Docker host as Mailcow is the recommended deployment for most installations.

Moolias remains a separate Compose project under `/opt/moolias`; it is **not** added to Mailcow's main `docker-compose.yml`. The application joins Mailcow's existing Docker network and Mailcow nginx proxies the public Moolias hostname to the internal `moolias-app:8000` endpoint.

This keeps the deployment simple while preserving a clear update and security boundary between Mailcow and Moolias.

## Resulting layout

```text
/opt/mailcow-dockerized
├── mailcow.conf
├── docker-compose.yml
└── data/conf/nginx/moolias.conf   # managed reverse-proxy site

/opt/moolias
├── .env                           # mode 0600
├── compose.yml                    # Moolias Mailcow-host deployment
├── update.sh
└── .moolias-mailcow-install
```

The installer also adds the required hardened Mailcow Agent as a separate Mailcow-side service. Its private state and dedicated Postfix/Rspamd policy files stay below `/opt/mailcow-dockerized`; they are not mounted into the Moolias application container.

Docker:

```text
Mailcow nginx ── Mailcow Docker network ── moolias-app:8000
      ▲                                     │
      │                                     └── moolias-data -> /data
      │
      ├── Moolias backend API/OAuth requests over the private network
      └── moolias-agent:8081 for authenticated Agent requests
```

The Moolias application and Mailcow Agent publish **no additional host ports** in this mode.

The `moolias-data` volume is persistent application state and is required even when usage statistics are disabled. Normal application/UI state may be stored there; optional statistics and Newsletter Management add their own data when enabled.

## Before you install

You need:

- a running Mailcow installation, normally in `/opt/mailcow-dockerized`;
- a dedicated DNS hostname for Moolias, for example `moolias.example.org`;
- a Mailcow **read/write API key**;
- a Mailcow OAuth2 client whose redirect URI is:

```text
https://moolias.example.org/oauth/callback
```

Do not reuse `MAILCOW_HOSTNAME` itself for Moolias. Give Moolias its own hostname.

### Mailcow API allowlist

Do not leave the API source restriction unspecified and do not enable **Skip IP check for API** for the normal same-host deployment.

Moolias runs as a container on Mailcow's existing Docker network. The API key should therefore allow the IPv4 CIDR of that network rather than one individual Moolias container address. A container address may change whenever the container is recreated.

A default Mailcow installation commonly uses:

```text
172.22.1.0/24
```

Do not copy that example blindly. The public Moolias bootstrap inspects the running `nginx-mailcow` container, finds the network whose Docker Compose label is `mailcow-network`, reads its configured IPv4 subnet and prints the exact CIDR value that should be entered in Mailcow before it asks for the API key.

The bootstrap also reads Mailcow's actual `HTTP_PORT` from `mailcow.conf`. The private backend URL therefore follows the real Mailcow installation instead of assuming a fixed port. Examples:

```text
HTTP_PORT=80    -> http://nginx-mailcow:80
HTTP_PORT=8080  -> http://nginx-mailcow:8080
```

The installer displays guidance similar to:

```text
Mailcow API access
-------------------
Docker network: mailcowdockerized_mailcow-network
Internal Mailcow URL: http://nginx-mailcow:80

Before entering the API key, create/use a READ/WRITE API key in Mailcow
and allow this Docker network:
  172.22.1.0/24

Leave "Skip IP check for API" disabled.
Do not allowlist the individual Moolias container IP.
```

After installation, the bootstrap performs a read-only Mailcow API request **from inside the running Moolias container** through this private backend URL. An invalid key, incorrect IP/CIDR allowlist or unreachable Mailcow nginx endpoint therefore fails before the installer prints its final completion summary.

## Recommended interactive installation

Run on the Mailcow host:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/install.sh \
  | sudo bash
```

The bootstrap installer follows the latest stable Moolias release by default. It asks only for values that cannot be derived safely:

1. public Moolias URL, with a suggested hostname derived from `MAILCOW_HOSTNAME`;
2. Mailcow read/write API key, after displaying the detected API allowlist CIDR;
3. OAuth client ID;
4. OAuth client secret;
5. whether Mailcow ACME should add the Moolias hostname to `ADDITIONAL_SAN`;
6. whether optional primary sender protection should be enabled through the required Mailcow Agent.

Secrets are read from `/dev/tty` without echo. The Mailcow Agent is installed in every standard Mailcow-host installation because guided alias creation and replacement depend on it. Its generated HMAC secret is copied directly into `/opt/moolias/.env`; there is no manual copy/paste step and the final summary never prints the secret value. Choosing `no` for primary sender protection disables only that optional capability, not the Agent itself.

Routine Docker Compose progress and successful nginx warning output are kept out of the normal completion flow. If an installation step actually fails, the captured error output is shown.

## Public and internal Mailcow URLs

The recommended same-host deployment deliberately keeps two URLs separate:

```dotenv
MAILCOW_URL=https://mail.example.org
MAILCOW_INTERNAL_URL=http://nginx-mailcow:80
```

`MAILCOW_URL` remains the public Mailcow URL. Browser-facing OAuth authorization is always sent there.

`MAILCOW_INTERNAL_URL` is generated by the installer from Mailcow's real `HTTP_PORT`. Moolias uses it for server-side Mailcow API requests and OAuth token/profile requests. This avoids public-DNS hairpin/NAT dependencies between two containers that already share a private Docker network.

The required Mailcow Agent likewise receives a private URL such as:

```dotenv
MOOLIAS_MAILCOW_AGENT_URL=http://nginx-mailcow:80/moolias-agent
```

If Newsletter Management is installed, its restricted agent likewise uses Mailcow nginx, normally through:

```dotenv
MOOLIAS_NEWSLETTER_AGENT_URL=http://nginx-mailcow:80/moolias-newsletter-agent
```

Standalone deployments may leave `MAILCOW_INTERNAL_URL` empty; Moolias then falls back to `MAILCOW_URL` for backend requests. A standalone Moolias application still needs the Mailcow Agent installed on the Mailcow host; an empty `MOOLIAS_MAILCOW_AGENT_URL` falls back to `<MAILCOW_URL>/moolias-agent`.

## What the installer changes

The main installer deliberately has a narrow scope.

It creates or manages:

- `/opt/moolias/.env`;
- `/opt/moolias/compose.yml`;
- `/opt/moolias/update.sh`;
- `/opt/moolias/.moolias-mailcow-install`;
- `/opt/mailcow-dockerized/data/conf/nginx/moolias.conf`.

The required Mailcow Agent installer additionally manages only its own marked/narrowly scoped Mailcow-side configuration, including:

- its `moolias-agent` Compose override block;
- `/opt/mailcow-dockerized/data/conf/moolias-agent/` for private Agent state;
- `/opt/mailcow-dockerized/data/conf/postfix/moolias-agent/` for its sender policy;
- `/opt/mailcow-dockerized/data/conf/rspamd/custom/moolias-agent/` for the exact-recipient first-mail bypass map;
- its marked nginx, Postfix and Rspamd integration files/blocks.

When Mailcow ACME is selected, the main installer also adds the Moolias hostname to `ADDITIONAL_SAN` in `mailcow.conf` and restarts `acme-mailcow` so the certificate can be refreshed.

Before replacing an installer-managed file, the installer creates a timestamped backup. It refuses to overwrite unrelated nginx, Compose, Postfix or Rspamd configuration that cannot be merged safely.

It does **not**:

- edit Mailcow's main `docker-compose.yml`;
- give Moolias or the Mailcow Agent the Docker socket;
- mount Mailcow configuration or database files into the Moolias application;
- expose a new application or Agent port on the host;
- reuse Mailcow database credentials.

Optional feature sidecars such as Newsletter Management manage their own narrowly scoped Mailcow configuration and Compose override blocks; those changes are documented in the corresponding feature documentation.

Browser-facing OAuth stays on the normal public Mailcow URL. Server-side API/OAuth traffic uses Mailcow nginx on the private Docker network when Moolias is installed on the Mailcow host.

## Mailcow Docker network discovery

The installer does not assume a Compose project name such as `mailcowdockerized`.

It finds the running `nginx-mailcow` container, inspects its attached networks and selects the network whose Docker Compose label is:

```text
com.docker.compose.network=mailcow-network
```

The discovered Docker network name is stored as `MAILCOW_DOCKER_NETWORK` in the Moolias `.env` file and used by the external network declaration in `compose.yml`.

The public bootstrap also reads the IPv4 subnet from this network and displays it for the Mailcow API-key source allowlist. `HTTP_PORT` is read from `mailcow.conf` with Mailcow's default of `80` when the setting is absent.

This also works when the Mailcow Compose project has a non-default project name or a non-default HTTP port.

## TLS modes

### Mailcow ACME

For a normal Mailcow installation with Let's Encrypt enabled, the installer can add the Moolias hostname to:

```dotenv
ADDITIONAL_SAN=moolias.example.org
```

Existing `ADDITIONAL_SAN` entries are preserved.

The installer refuses this mode when `SKIP_LETS_ENCRYPT` or `ONLY_MAILCOW_HOSTNAME` makes the requested SAN ineffective. In that case use external TLS or adjust the Mailcow certificate policy manually first.

Make sure the Moolias DNS record points to the Mailcow host before expecting certificate issuance to succeed.

After restarting `acme-mailcow`, the public bootstrap waits briefly for Mailcow's certificate file to contain the Moolias hostname. The final status reports either:

```text
TLS certificate:   OK
```

or:

```text
TLS certificate:   PENDING
```

A `PENDING` result means the application is installed but the new certificate has not been activated yet. **Do not bypass the browser certificate warning.** Check Mailcow ACME instead:

```bash
cd /opt/mailcow-dockerized
docker compose logs --tail=50 acme-mailcow
```

The wait can be adjusted for automation with `MOOLIAS_TLS_WAIT_SECONDS`; the installer caps it at ten minutes.

### Existing certificate or external reverse proxy

Choose external TLS when Mailcow ACME is disabled or TLS is terminated by another reverse proxy.

The installer still creates the dedicated Mailcow nginx virtual host but leaves `mailcow.conf` certificate settings untouched. Your existing certificate/reverse proxy must cover the Moolias hostname.

The generated HTTP virtual host preserves an incoming `X-Forwarded-Proto: https`, so an external TLS proxy may forward to Mailcow over HTTP without creating a redirect loop.

## Mailcow Agent and optional primary sender protection

The Mailcow Agent is required for guided alias creation and replacement. It owns the short-lived exact-recipient first-mail delivery bypass and runs its expiry independently of an open browser session. The main installer therefore installs or updates this Agent every time; it is not an optional sidecar anymore.

The Agent remains a separate hardened service because it needs narrowly scoped write access to its private state, dedicated Postfix sender policy and dedicated Rspamd recipient-bypass map. The main Moolias application never receives those mounts.

Primary sender protection remains optional. The setup question controls only `MOOLIAS_SENDER_PROTECTION`; answering `no` keeps the required Agent installed while leaving primary sender protection disabled.

The installer reads the generated or preserved Agent secret directly from Mailcow's private Agent environment file, writes it to `/opt/moolias/.env` as `MOOLIAS_MAILCOW_AGENT_SECRET`, configures the private Mailcow-nginx Agent URL and starts Moolias with that shared secret. The integrated completion summary reports only that the secret was stored safely; it does not print the secret or ask the administrator to copy it manually.

See [Mailcow Agent and primary sender protection](sender-protection.md) for its security model, first-mail bypass and Postfix behavior.

## Optional Newsletter Management

Newsletter Management needs a separate restricted sidecar because the Moolias web application deliberately has no access to Dovecot mail storage or the Docker socket. For an exact mailbox + Message-ID, the sidecar normally returns only the fixed newsletter-related headers. Only when Rspamd has marked that exact message with Moolias's body-unsubscribe signal may the sidecar inspect the message text locally; in that case it returns only an extracted HTTPS unsubscribe URL and never returns the message body.

Install Newsletter Management on the Mailcow host **after the normal Moolias installation** with the stable-aware bootstrap:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/install-newsletter.sh \
  | sudo bash
```

The small bootstrap resolves the latest stable Moolias release and downloads the Newsletter Agent installer, the Rspamd installer and the Lua detector from that same release tag. This prevents mixing an unreleased `main` component with a stable Moolias installation.

The installer:

- configures the restricted Dovecot/Newsletter Agent integration;
- adds the hardened `moolias-newsletter-agent` sidecar to Mailcow's Compose override;
- exposes the agent only through Mailcow nginx, without a published host port;
- installs and validates the zero-score `MOOLIAS_BODY_UNSUB` Rspamd detector;
- updates `/opt/moolias/.env` with the generated agent secret, private agent URL and `MOOLIAS_NEWSLETTER_MANAGEMENT=true`;
- recreates the standard Moolias application container so the new feature setting becomes active.

The Newsletter Agent follows the same configured Moolias image/tag as the normal installation by default. An explicit `MOOLIAS_AGENT_IMAGE` override is intended for development and integration testing.

The global switch only makes the feature available. It does **not** automatically enable Newsletter Management for every mailbox. The effective mailbox state follows Mailcow tags, analogous to usage statistics. With the default tag family:

```text
moolias-newsletter       = enabled
moolias-newsletter-off   = disabled
```

A mailbox tag overrides the domain tag; without a mailbox newsletter tag, the domain setting is inherited. With neither tag, the safe default is off. An administrator can therefore enable `moolias-newsletter` on a domain as the default, or users can explicitly select **On**, **Off**, or **Use domain setting** for their own mailbox in Moolias Settings.

When a Moolias settings change makes the effective state switch from off to on, Moolias asks whether still-available historical Rspamd/Dovecot data should also be evaluated or whether detection should start only from that point forward. There is no extra prompt at login.

Turning `MOOLIAS_NEWSLETTER_MANAGEMENT=false` later disables the feature server-wide and greys out the mailbox control, but it does not delete Mailcow newsletter tags or already stored newsletter metadata.

See [Newsletter management](newsletter-management.md) for the complete policy, privacy, linked-mailbox and security model.

## Re-running the installer

The installer is intended to be safe to run again.

Existing Moolias secrets and optional application settings are preserved unless replacement values are explicitly supplied through environment variables. Managed files are backed up before replacement.

A re-run also rediscovers the current Mailcow Docker network and `HTTP_PORT`, which is useful after a Mailcow Compose/project-name or port migration. If it finds the published v1.2.1 `moolias-sender-agent` layout, it migrates its secret and version-1 state into the unified `moolias-agent` layout before retiring the old managed service/files.

## Updating Moolias

After installation:

```bash
cd /opt/moolias
./update.sh
```

The updater uses the local `compose.yml`, pulls the latest stable image, waits for Moolias to become healthy and retains its existing rollback behavior.

When an existing Mailcow-host installation still has the v1.2.1/old sender-agent layout and therefore lacks `MOOLIAS_MAILCOW_AGENT_SECRET`, the updater stops **before recreating** Moolias. Run the recommended installer once:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/install.sh \
  | sudo bash
```

The installer preserves the old Agent secret and sender-protection state, validates the replacement Agent and Mailcow configuration, then archives the old managed state/policy directories. Normal `./update.sh` operation can be used afterwards.

## Backup

Aliases and Newsletter Management policy tags remain stored in Mailcow.

Always back up the persistent Moolias `/data` volume. The default local application/statistics database is:

```text
/data/moolias-stats.sqlite3
```

Despite its historical name, this SQLite file may also contain normal application/UI state and remains required even when `MOOLIAS_USAGE_STATS=false`. If Newsletter Management is enabled, also include its default metadata and collector-state database:

```text
/data/moolias-newsletters.sqlite3
```

Use a SQLite-consistent backup rather than copying live database files while WAL mode is active.

Also back up `/opt/moolias/.env`; it contains the Mailcow API key, OAuth secret, Moolias session secret and required Mailcow Agent secret, plus optional feature secrets.

## Non-interactive installation

Automation is supported, but all required values must be explicit. For automation, configure the API-key allowlist before running the bootstrap. You can determine the Mailcow Docker-network CIDR with `docker network inspect`, or run the public bootstrap interactively once to see the detected value.

Use the root bootstrap so network/port discovery, private backend configuration and final validation remain identical to the interactive installation:

```bash
sudo env \
  MOOLIAS_NONINTERACTIVE=true \
  MOOLIAS_BASE_URL=https://moolias.example.org \
  MAILCOW_URL=https://mail.example.org \
  MAILCOW_API_KEY='...' \
  MAILCOW_OAUTH_CLIENT_ID='...' \
  MAILCOW_OAUTH_CLIENT_SECRET='...' \
  MOOLIAS_TLS_MODE=mailcow-acme \
  MOOLIAS_INSTALL_SENDER_PROTECTION=no \
  bash install.sh
```

`MOOLIAS_INSTALL_SENDER_PROTECTION=no` disables only optional primary sender protection. The required Mailcow Agent is still installed and its secret is written to the Moolias `.env` file.

Useful installer overrides:

```text
MAILCOW_DIR=/opt/mailcow-dockerized
MOOLIAS_INSTALL_DIR=/opt/moolias
MOOLIAS_INSTALL_REF=v1.2.3
MOOLIAS_IMAGE_TAG=latest
MOOLIAS_TLS_MODE=mailcow-acme|external|none
MOOLIAS_INSTALL_SENDER_PROTECTION=yes|no
MOOLIAS_TLS_WAIT_SECONDS=90
```

`MOOLIAS_SOURCE_DIR` and `MOOLIAS_SKIP_PULL` exist for development/integration testing and are not needed for normal production installation.

## Standalone deployment

Moolias still supports installation on another Docker host. The repository `compose.yml` publishes the configured host port and can be placed behind Caddy, nginx, Traefik or another HTTPS reverse proxy.

Use the standalone method when:

- application workloads are intentionally separated from the Mailcow host;
- an existing container platform should run Moolias;
- Mailcow's nginx/ACME stack should not serve the Moolias hostname.

The Mailcow Agent remains required and must be installed on the Mailcow host even when the Moolias application runs elsewhere. Copy its `MOOLIAS_MAILCOW_AGENT_SECRET` into the standalone application's `.env`; by default the application reaches it through `<MAILCOW_URL>/moolias-agent`.

The application behavior and updater are otherwise the same in both deployment modes. Newsletter Management still requires its separate restricted agent to be installed on the Mailcow host because Dovecot remains the source of original newsletter metadata.
