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

By default, Moolias does not need its own user database. Optional usage statistics use a local SQLite database for counters, sender aggregates and review state; the aliases themselves remain in mailcow.

## Features

- Create aliases on the user's own mailcow domain.
- Choose between name-based aliases such as `amazon-k7`, readable random aliases such as `hafen-feder-27`, or a custom local part.
- Add a purpose or description to each alias.
- Enable and disable aliases without deleting them.
- Replace an alias while keeping the old address disabled for traceability.
- Optionally expose individual aliases as selectable SOGo sender addresses.
- Prepare offline aliases in advance and assign them later after they have been used.
- Detect catch-all delivery and warn when it weakens the one-alias-per-service model.
- Search, filter and manage aliases from one responsive dashboard.
- Review used offline aliases, unexpected senders and collector warnings in the **Action required / Handlungsbedarf** view.
- Optionally collect received/sent usage counters and sender information with configurable privacy levels.
- Review sender identities that do not match the expected use of an alias and mark them as expected or unexpected.
- Monitor the health and Rspamd-history coverage of the optional statistics collector.
- German and English interface.
- Installable web-app experience on supported desktop and mobile browsers.

## Installation

### Requirements

You need:

- a running mailcow installation that Moolias can reach;
- Docker with Docker Compose;
- a hostname for Moolias served over HTTPS;
- mailcow administrator access to create an OAuth2 client and a read/write API key.

### 1. Clone the repository

```bash
git clone https://github.com/vain90/Moolias.git
cd Moolias
cp .env.example .env
```

### 2. Create a mailcow OAuth2 client

In the mailcow administration interface, open **Configuration -> Access -> OAuth2** and create a client with this redirect URI:

```text
https://aliases.example.com/oauth/callback
```

Replace `aliases.example.com` with the hostname you will use for Moolias, then copy the generated client ID and client secret into `.env`.

Keep the mailcow OAuth redirect URI on `/oauth/callback`. Moolias processes the OAuth response at that endpoint and then sends the authenticated user to the **Overview** page. `/overview` itself is not an OAuth callback URL.

### 3. Create a mailcow API key

Create a **read/write** API key in mailcow. Moolias needs it to create and manage aliases and, when usage-statistics self-service is enabled, to update the authenticated mailbox's statistics tags.

Restrict the API key to the Moolias server's source IP whenever your network design allows it.

### 4. Configure Moolias

At minimum, set these values in `.env`:

```dotenv
MOOLIAS_BASE_URL=https://aliases.example.com
MOOLIAS_SESSION_SECRET=<random-secret>
MOOLIAS_TRUSTED_HOSTS=aliases.example.com

MAILCOW_URL=https://mail.example.com
MAILCOW_API_KEY=<read-write-api-key>
MAILCOW_OAUTH_CLIENT_ID=<oauth-client-id>
MAILCOW_OAUTH_CLIENT_SECRET=<oauth-client-secret>
```

Generate a strong session secret with:

```bash
openssl rand -hex 32
```

See [.env.example](.env.example) for the complete configuration reference and all optional settings.

### 5. Start Moolias

```bash
docker compose pull
docker compose up -d
```

The repository Compose file publishes Moolias on host port `8080` by default. Put your normal HTTPS reverse proxy, such as Caddy, nginx or Traefik, in front of it and forward requests to Moolias.

Then open your configured `MOOLIAS_BASE_URL` and sign in through mailcow. After successful authentication, Moolias opens the **Overview** page.

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

When sender detail is enabled, Moolias can flag sender identities that appear unrelated to an alias and let the user review them. This is a traceability feature, not spam classification or threat intelligence.

Statistics and review state are stored in the persistent SQLite database configured by `MOOLIAS_USAGE_DB_PATH`. Alias configuration remains in mailcow.

The dashboard also reports collector health and warns when Rspamd history coverage may be too small, stale or interrupted. See [Statistics collector health](docs/statistics-collector-health.md) for the operational details.

### Offline aliases

Moolias can prepare aliases before they are needed. They can be copied to a phone or password manager and handed out even when Moolias is not currently reachable.

Once a prepared address has been used, Moolias can surface it in **Action required / Handlungsbedarf** so a purpose can be assigned. The address itself does not change when it is assigned.

### Install as a web app

Moolias includes a web-app manifest and icons. On supported platforms it can be installed from the browser, for example with **Add to Home Screen** on iPhone/iPad or **Add to Dock** in Safari on macOS.

The installed app uses the same Moolias server and mailcow OAuth login as the normal browser version.

## Updating

For deployments following the stable release channel:

```bash
./update.sh
```

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

Manual Docker Compose updates remain possible:

```bash
docker compose pull
docker compose up -d
```

Existing pre-release installations from before the rename should follow [the Moolias migration guide](docs/migration-to-moolias.md) once.

## Security

Moolias holds a privileged mailcow read/write API key. Keep the API key and OAuth credentials on the server, use HTTPS, use secure cookies in production and restrict the API key by source IP where possible.

Alias ownership is validated server-side before Moolias modifies an existing alias.

See [SECURITY.md](SECURITY.md) for deployment recommendations and vulnerability reporting.

## Development

Development setup, test commands and contribution guidelines are documented in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Moolias is licensed under the [MIT License](LICENSE).
