# Moolias

**Self-hosted privacy aliases for mailcow.**

Fighting spam is hard. Even with good filtering, email addresses eventually end up in places where they should not be: a service gets breached, customer data is shared or sold, or an address simply finds its way onto a spam list. Once your primary email address is circulating, getting it back under control can be almost impossible.

Moolias takes a different approach: **do not give out your real mailbox address at all.**

Treat your real mailbox address like a private identifier, not an address you hand out to every website. Instead, create a separate alias for every service you use:

```text
Amazon  -> amazon-k7@example.org --------\
Hotel   -> hotel-feder-27@example.org -----+-> alice@example.org
Shop    -> shop-wald-42@example.org -------/
```

All of these addresses deliver to the same private mailbox, while the mailbox address itself stays hidden.

If one alias starts receiving spam, you can disable or replace only that address without affecting anything else. And because every service has its own alias, you can immediately see which service you gave the affected address to — a strong indication of where it was leaked, shared or sold.

**One service. One alias. Your mailbox stays private.**

If you know Apple Hide My Email, the basic idea will feel familiar — but Moolias applies it to your own mailcow domains and infrastructure.

Moolias is not a spam filter. It makes exposed addresses isolated, traceable and replaceable instead of letting one leaked primary address become a permanent problem.

> Moolias is under active development. Review the security and deployment notes before using it in an Internet-facing environment.

## How it works

mailcow remains the source of truth for alias data. Moolias authenticates users through mailcow OAuth2 and uses the mailcow API to manage aliases on behalf of the signed-in mailbox.

A user can manage only aliases that belong exclusively to their authenticated mailbox. Moolias derives the alias domain and forwarding target on the server instead of accepting them from the browser.

Moolias does not maintain a separate account or identity database; Mailcow remains the identity source. Moolias does use persistent local SQLite state for application/UI data. Optional usage statistics add counters and sender aggregates, while optional Newsletter Management uses a separate newsletter database for detected newsletter metadata, unsubscribe information and its historical-import watermark. Newsletter enablement itself remains a Mailcow domain/mailbox tag policy rather than a local database preference. Alias configuration itself remains in Mailcow.

## Features

- Create aliases on the user's own mailcow domain.
- Choose between name-based aliases such as `amazon-k7`, readable random aliases such as `hafen-feder-27`, or a custom local part.
- Add a purpose or description to each alias.
- Enable and disable aliases without deleting them.
- Replace an alias while keeping the old address active until the chosen deactivation policy completes the migration.
- Optionally expose individual aliases as selectable SOGo sender addresses.
- Prepare offline aliases in advance and assign them later after they have been used.
- Detect catch-all delivery and warn when it weakens the one-alias-per-service model.
- Search, filter and manage aliases from one responsive dashboard.
- Review used offline aliases, unexpected senders and collector warnings in the **Action required / Handlungsbedarf** view.
- Optionally collect received/sent usage counters and sender information with configurable privacy levels.
- Review sender identities that do not match the expected use of an alias and mark them as expected or unexpected.
- Monitor the health and Rspamd-history coverage of the optional statistics collector.
- Optionally detect newsletters and subscriptions, show the alias that received them and expose safe unsubscribe actions.
- Control Newsletter Management through an inheritable Mailcow domain/mailbox tag policy, analogous to usage statistics.
- German and English interface.
- Installable web-app experience on supported desktop and mobile browsers.

## Installation

### Recommended: install on the Mailcow host

For most installations, run Moolias on the same Docker host as Mailcow. Moolias stays a **separate Compose project** under `/opt/moolias`; it does not modify Mailcow's main `docker-compose.yml` and it does not publish another host port.

Instead, the installer joins Moolias to Mailcow's existing Docker network and creates a dedicated Mailcow nginx virtual host that proxies internally to Moolias.

You need:

- a running Mailcow installation, normally `/opt/mailcow-dockerized`;
- a dedicated DNS hostname such as `moolias.example.org`;
- a Mailcow **read/write API key**;
- a Mailcow OAuth2 client.

Create the OAuth2 client in **Configuration -> Access -> OAuth2** with this redirect URI:

```text
https://moolias.example.org/oauth/callback
```

Then run on the Mailcow host:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/install.sh \
  | sudo bash
```

The small bootstrap prefers installer files from the latest stable release. During the first release transition for a newer installer it can safely fall back to the installer files on `main`; the Moolias application image still stays on the stable `latest` channel.

The guided installer:

- detects the Mailcow installation and the real Mailcow Docker network;
- suggests a Moolias hostname based on `MAILCOW_HOSTNAME`;
- generates a strong Moolias session secret automatically;
- reads API/OAuth secrets without echoing or printing them;
- creates `/opt/moolias` with a private `.env`, Compose file and updater;
- starts the stable Moolias image without a published host port;
- creates and validates a dedicated Mailcow nginx reverse-proxy site;
- installs the hardened Mailcow Agent required by guided alias creation and replacement;
- can optionally enable primary sender protection through that Agent;
- can optionally add the Moolias hostname to Mailcow `ADDITIONAL_SAN` for Mailcow ACME;
- can optionally install the restricted Newsletter Agent and enable Newsletter Management in the same fresh interactive run;
- backs up installer-managed files before replacing them;
- validates Docker Compose, Moolias health and Mailcow nginx before completing.

After installation, open the configured Moolias URL and sign in through Mailcow. If Newsletter Management is not enabled during the initial guided run, it can still be installed later with the separate stable-aware Newsletter installer.

See **[Install Moolias on the Mailcow host](docs/install-on-mailcow.md)** for TLS modes, non-interactive installation, backups and the exact files the installer manages.

### Alternative: standalone Docker host

Moolias can also run on another Docker host or container platform. This is useful when application workloads are intentionally separated from the Mailcow server or an existing reverse proxy should own the Moolias hostname.

The Mailcow Agent is still required because guided alias creation and replacement use its exact-recipient first-mail delivery bypass. Install the Agent on the Mailcow host first:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install-mailcow-agent.sh \
  | sudo env MOOLIAS_AGENT_IMAGE=ghcr.io/vain90/moolias:latest bash
```

Keep the `MOOLIAS_MAILCOW_AGENT_SECRET` printed by the installer private; it is needed by the standalone Moolias application.

On the application host:

```bash
git clone https://github.com/vain90/Moolias.git
cd Moolias
cp .env.example .env
```

Configure at least:

```dotenv
MOOLIAS_BASE_URL=https://moolias.example.org
MOOLIAS_SESSION_SECRET=<random-secret>
MOOLIAS_TRUSTED_HOSTS=moolias.example.org
MOOLIAS_MAILCOW_AGENT_SECRET=<secret-printed-by-the-mailcow-agent-installer>

MAILCOW_URL=https://mail.example.org
MAILCOW_API_KEY=<read-write-api-key>
MAILCOW_OAUTH_CLIENT_ID=<oauth-client-id>
MAILCOW_OAUTH_CLIENT_SECRET=<oauth-secret>
```

By default Moolias reaches the Agent at `<MAILCOW_URL>/moolias-agent`. Set `MOOLIAS_MAILCOW_AGENT_URL` only when the Agent is exposed at a different URL.

Generate a session secret with:

```bash
openssl rand -hex 32
```

The OAuth redirect URI remains:

```text
https://moolias.example.org/oauth/callback
```

Then start Moolias:

```bash
docker compose pull
docker compose up -d
```

The standalone `compose.yml` publishes port `8080` by default. Put Caddy, nginx, Traefik or another HTTPS reverse proxy in front of it.

See [.env.example](.env.example) for all configuration values.

## Optional configuration

### Restrict access with a mailcow tag

By default, every successfully authenticated mailcow mailbox can use Moolias. To restrict access, configure a tag:

```dotenv
MOOLIAS_ACCESS_TAG=moolias
```

Assign the same tag to an allowed mailbox or domain in mailcow. Moolias checks access after authentication and keeps mailbox ownership isolated even when multiple users share the same domain.

### Usage statistics and sender review

Usage statistics are globally disabled by default:

```dotenv
MOOLIAS_USAGE_STATS=false
```

Enable them with:

```dotenv
MOOLIAS_USAGE_STATS=true
```

The default statistics policy uses the `moolias-stats` tag family and supports four privacy levels:

| Mode | Stored information |
| --- | --- |
| `off` | No new usage statistics |
| `basic` | Received and sent counters |
| `domain` | Counters plus sender-domain aggregates |
| `full` | Counters plus full sender-address aggregates |

A mailbox can override its domain's statistics mode; otherwise it inherits the domain setting. Users can change only their own statistics mode through Moolias.

Increasing the detail level can optionally evaluate the still-available Mailcow/Rspamd history. Reducing the detail level requires confirmation because Moolias immediately collapses or deletes already stored details that the new privacy mode no longer permits. The interface shows a processing state while either operation is running.

When sender detail is enabled, Moolias can flag sender identities that appear unrelated to an alias and let the user review them. This is a traceability feature, not spam classification or threat intelligence.

Statistics and review state use the persistent SQLite database configured by `MOOLIAS_USAGE_DB_PATH`. This database is also used for normal Moolias application/UI state and therefore remains required when `MOOLIAS_USAGE_STATS=false`; disabling statistics stops the collector and new statistics collection, not the persistent local state database. Alias configuration remains in mailcow.

The dashboard also reports collector health and warns when Rspamd history coverage may be too small, stale or interrupted. See [Usage statistics](docs/statistics.md) and [Statistics collector health](docs/statistics-collector-health.md) for the operational details.

### Newsletter management

Newsletter Management is globally disabled by default:

```dotenv
MOOLIAS_NEWSLETTER_MANAGEMENT=false
```

For a fresh recommended same-host installation, the guided installer can install the restricted Mailcow Newsletter Agent and enable the server-side feature in the same run. If that option is skipped, Newsletter Management can still be enabled later with the separate stable-aware Newsletter installer. Actual enablement for each mailbox then follows the same Mailcow tag inheritance model as statistics. With the default `MOOLIAS_NEWSLETTER_TAG=moolias-newsletter`, `moolias-newsletter` enables the feature and `moolias-newsletter-off` disables it. A mailbox tag overrides the domain tag; without a mailbox newsletter tag, the domain setting is inherited.

There is no additional prompt at login. Users can choose **Use domain setting**, **Off**, or **On** in Settings, and Moolias modifies only that newsletter tag family on their own mailbox.

When a settings change makes the effective state switch from off to on, Moolias asks whether still-available historical Rspamd/Dovecot data should be imported or whether detection should start only from that point forward. The question is shown only for a real effective off-to-on transition.

If the administrator disables `MOOLIAS_NEWSLETTER_MANAGEMENT` server-wide, controls are greyed out and discovery/actions stop regardless of Mailcow tags. The tags and already detected newsletter data are retained.

Detected newsletter metadata, up to the three newest distinct unsubscribe URLs and the operational historical-import watermark are stored in `MOOLIAS_NEWSLETTER_DB_PATH`. The enable/disable policy itself is stored only as Mailcow domain/mailbox tags.

See [Newsletter management](docs/newsletter-management.md) for discovery, privacy, agent installation and RFC 8058 one-click details.

### Offline aliases

Moolias can prepare aliases before they are needed. They can be copied to a phone or password manager and handed out even when Moolias is not currently reachable.

Once a prepared address has been used, Moolias can surface it in **Action required / Handlungsbedarf** so a purpose can be assigned. The address itself does not change when it is assigned.

### Primary sender protection

Primary sender protection is optional. It prevents a signed-in mailbox user from sending with the mailbox's primary address while normal aliases continue through Mailcow's standard sender policy.

The Mailcow Agent itself is required for guided alias creation and replacement and is installed automatically by the recommended Mailcow-host installer. Primary sender protection is an optional capability of that already installed hardened Agent; enabling it does not give the Moolias application Docker, Mailcow API or database access beyond its existing application credentials.

See [Mailcow Agent and primary sender protection](docs/sender-protection.md) for the security model, migration of existing rules and manual installation details.

### Install as a web app

Moolias includes a web-app manifest and icons. On supported platforms it can be installed from the browser, for example with **Add to Home Screen** on iPhone/iPad or **Add to Dock** in Safari on macOS.

The installed app uses the same Moolias server and mailcow OAuth login as the normal browser version.

## Updating

For deployments following the stable release channel:

```bash
./update.sh
```

The recommended Mailcow-host installer places the updater in `/opt/moolias`, so the normal update is:

```bash
cd /opt/moolias
./update.sh
```

Existing Mailcow-host installations from v1.2.1 or an older sender-agent layout need one installer rerun when first moving to a release that requires the unified Mailcow Agent. The updater detects the missing Agent secret before changing the running application and tells you to run:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/install.sh \
  | sudo bash
```

That migration preserves the existing sender-protection secret and state, replaces only Moolias-managed Agent files/Compose blocks and then allows normal `./update.sh` use again.

Check whether an update is available without changing the running deployment:

```bash
./update.sh --check
```

To deliberately run the current unreleased `main` build from the `edge` image:

```bash
./update.sh --beta
```

Run `./update.sh --help` for all updater options.

The default Docker image tag is `latest`. A fixed release can be pinned with `MOOLIAS_TAG`, while `edge` follows the current `main` branch. See [.env.example](.env.example) for details.

Manual Docker Compose updates remain possible after the required Mailcow Agent is configured:

```bash
docker compose pull
docker compose up -d
```

Existing pre-release installations from before the rename should follow [the Moolias migration guide](docs/migration-to-moolias.md) once.

## Security

Moolias holds a privileged Mailcow read/write API key. Keep the API key and OAuth credentials on the server, use HTTPS, use secure cookies in production and restrict API access to the Moolias source network/address where practical.

The recommended Mailcow-host deployment shares only Mailcow's Docker network with the main application. Moolias does not receive the Docker socket, Mailcow database credentials, Postfix configuration or other Mailcow filesystem mounts. The separate Mailcow Agent receives only its private state plus the dedicated Postfix and Rspamd policy paths it manages.

Alias ownership is validated server-side before Moolias modifies an existing alias.

See [SECURITY.md](SECURITY.md) for deployment recommendations and vulnerability reporting.

## Development

Development setup, test commands and contribution guidelines are documented in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Moolias is licensed under the [MIT License](LICENSE).
