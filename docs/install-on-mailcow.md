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

Docker:

```text
Mailcow nginx ── Mailcow Docker network ── moolias-app:8000
                                            │
                                            └── moolias-data -> /data
```

The Moolias application publishes **no host port** in this mode.

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

For the API key, restrict access to the Mailcow/Moolias host or Docker source range where practical.

## Recommended interactive installation

Run on the Mailcow host:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install.sh \
  | sudo bash
```

The bootstrap installer follows the latest stable Moolias release by default. It asks only for values that cannot be derived safely:

1. public Moolias URL, with a suggested hostname derived from `MAILCOW_HOSTNAME`;
2. Mailcow read/write API key;
3. OAuth client ID;
4. OAuth client secret;
5. whether Mailcow ACME should add the Moolias hostname to `ADDITIONAL_SAN`;
6. whether the optional primary-sender protection should be installed now.

Secrets are read from `/dev/tty` without echo and are never printed in the completion summary.

## What the installer changes

The installer deliberately has a narrow scope.

It creates or manages:

- `/opt/moolias/.env`;
- `/opt/moolias/compose.yml`;
- `/opt/moolias/update.sh`;
- `/opt/moolias/.moolias-mailcow-install`;
- `/opt/mailcow-dockerized/data/conf/nginx/moolias.conf`.

When Mailcow ACME is selected, it also adds the Moolias hostname to `ADDITIONAL_SAN` in `mailcow.conf` and restarts `acme-mailcow` so the certificate can be refreshed.

Before replacing an installer-managed file, the installer creates a timestamped `before-moolias-*.bak` copy. It refuses to overwrite an unrelated nginx `moolias.conf` or an unmanaged existing `/opt/moolias` installation.

It does **not**:

- edit Mailcow's main `docker-compose.yml`;
- give Moolias the Docker socket;
- mount Mailcow configuration or database files into the Moolias application;
- expose a new application port on the host;
- reuse Mailcow database credentials.

Moolias reaches Mailcow through the normal HTTPS/API interface and OAuth2. The only shared runtime resource is Mailcow's Docker network.

## Mailcow Docker network discovery

The installer does not assume a Compose project name such as `mailcowdockerized`.

It finds the running `nginx-mailcow` container, inspects its attached networks and selects the network whose Docker Compose label is:

```text
com.docker.compose.network=mailcow-network
```

The discovered Docker network name is stored as `MAILCOW_DOCKER_NETWORK` in the Moolias `.env` file and used by the external network declaration in `compose.yml`.

This also works when the Mailcow Compose project has a non-default project name.

## TLS modes

### Mailcow ACME

For a normal Mailcow installation with Let's Encrypt enabled, the installer can add the Moolias hostname to:

```dotenv
ADDITIONAL_SAN=moolias.example.org
```

Existing `ADDITIONAL_SAN` entries are preserved.

The installer refuses this mode when `SKIP_LETS_ENCRYPT` or `ONLY_MAILCOW_HOSTNAME` makes the requested SAN ineffective. In that case use external TLS or adjust the Mailcow certificate policy manually first.

Make sure the Moolias DNS record points to the Mailcow host before expecting certificate issuance to succeed.

### Existing certificate or external reverse proxy

Choose external TLS when Mailcow ACME is disabled or TLS is terminated by another reverse proxy.

The installer still creates the dedicated Mailcow nginx virtual host but leaves `mailcow.conf` certificate settings untouched. Your existing certificate/reverse proxy must cover the Moolias hostname.

The generated HTTP virtual host preserves an incoming `X-Forwarded-Proto: https`, so an external TLS proxy may forward to Mailcow over HTTP without creating a redirect loop.

## Optional primary sender protection

The main installer can run the existing Mailcow Agent installer as an optional final step.

The sender agent remains a separate hardened sidecar because it needs narrowly scoped write access to its dedicated Postfix policy and state directories. The main Moolias application never receives those mounts.

If enabled during installation, the main installer reads the generated agent secret directly from Mailcow's private agent environment file, writes it to `/opt/moolias/.env`, and recreates only the Moolias application container.

If you skip it, Moolias works normally and sender protection can be installed later.

See [Primary sender protection](sender-protection.md) for its security model and Postfix behavior.

## Re-running the installer

The installer is intended to be safe to run again.

Existing Moolias secrets and optional application settings are preserved unless replacement values are explicitly supplied through environment variables. Managed files are backed up before replacement.

A re-run also rediscovers the current Mailcow Docker network, which is useful after a Mailcow Compose/project-name migration.

## Updating Moolias

After installation:

```bash
cd /opt/moolias
./update.sh
```

The updater uses the local `compose.yml`, pulls the latest stable image, waits for Moolias to become healthy and retains its existing rollback behavior.

## Backup

Aliases remain stored in Mailcow.

When usage statistics are enabled, back up the Moolias `/data` volume as well. The default SQLite database is:

```text
/data/moolias-stats.sqlite3
```

Use a SQLite-consistent backup rather than copying a live database file while WAL mode is active.

Also back up `/opt/moolias/.env`; it contains the Mailcow API key, OAuth secret and Moolias session secret.

## Non-interactive installation

Automation is supported, but all required values must be explicit. Example:

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
  bash scripts/install.sh
```

Useful installer overrides:

```text
MAILCOW_DIR=/opt/mailcow-dockerized
MOOLIAS_INSTALL_DIR=/opt/moolias
MOOLIAS_INSTALL_REF=v1.2.3
MOOLIAS_IMAGE_TAG=latest
MOOLIAS_TLS_MODE=mailcow-acme|external|none
MOOLIAS_INSTALL_SENDER_PROTECTION=yes|no
```

`MOOLIAS_SOURCE_DIR` and `MOOLIAS_SKIP_PULL` exist for development/integration testing and are not needed for normal production installation.

## Standalone deployment

Moolias still supports installation on another Docker host. The repository `compose.yml` publishes the configured host port and can be placed behind Caddy, nginx, Traefik or another reverse proxy.

Use the standalone method when:

- application workloads are intentionally separated from the Mailcow host;
- an existing container platform should run Moolias;
- Mailcow's nginx/ACME stack should not serve the Moolias hostname.

The application behavior and updater are the same in both deployment modes.
