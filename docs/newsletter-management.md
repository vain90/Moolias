# Newsletter management

Moolias can detect newsletter and mailing-list messages from Mailcow's Rspamd history and expose a compact unsubscribe view for each Moolias mailbox.

The feature is disabled by default and has two independent enablement levels:

1. An administrator makes newsletter management available server-wide with `MOOLIAS_NEWSLETTER_MANAGEMENT=true` and installs the restricted Newsletter Agent.
2. Each authenticated mailbox decides for itself whether newsletter management should be enabled for that mailbox.

The effective state is therefore **server enabled AND mailbox enabled**.

## Mailbox opt-in

When newsletter management becomes available on the server and a mailbox has not made a choice yet, Moolias asks that mailbox once whether it wants to enable the feature. The answer is stored per authenticated mailbox address and can later be changed in Settings.

If the administrator sets `MOOLIAS_NEWSLETTER_MANAGEMENT=false`:

- newsletter discovery and unsubscribe actions are disabled for every mailbox
- the mailbox switch is shown disabled/greyed with a server-side-disabled explanation
- previously stored mailbox choices are retained
- re-enabling the server feature restores each mailbox's previous choice

If a mailbox disables newsletter management for itself, Moolias stops scheduling newsletter scans for that mailbox. Existing newsletter records are retained and become visible again if the mailbox later re-enables the feature.

The per-mailbox choice is stored in the persistent local Moolias SQLite database configured by `MOOLIAS_USAGE_DB_PATH`. Despite the variable name, this database is also used for normal Moolias mailbox preferences and is therefore required even when usage statistics are disabled.

## User experience

The Newsletter page shows one compact row per detected sender and recipient alias. The row includes the sender, the alias that received the message, the observed message count, the most recent message and the available unsubscribe action.

The Newsletter navigation entry is shown only when the feature is effectively enabled for the signed-in mailbox. When the server feature is available but the mailbox has disabled it, the mailbox can re-enable it from Settings.

The details control expands technical information only when it is needed.

A detected sender remains visible even when Moolias cannot recover a usable HTTPS unsubscribe URL. In that case the direct unsubscribe button is disabled. This can happen when the original message has already been deleted from Dovecot.

## Discovery flow

Moolias deliberately does not scan complete message bodies.

1. Moolias reads the configured Rspamd history window through the existing Mailcow API integration.
2. A message is considered a candidate when Rspamd recorded the mailing-list signal `MAILLIST` or the header signal `HAS_LIST_UNSUB`, the message was accepted without a spam action, and Rspamd has an authentication signal such as DKIM or DMARC allow. Rspamd history may expose symbols either as structured data or as scored strings such as `MAILLIST(-0.18)[generic]`; Moolias normalises both forms.
3. Moolias associates the Rspamd SMTP recipient with the authenticated user's mailbox or one of that user's Mailcow aliases.
4. The restricted Newsletter Agent asks Dovecot for a fixed set of headers for the exact mailbox and Message-ID.
5. Moolias extracts HTTPS and `mailto:` targets from `List-Unsubscribe` and checks `List-Unsubscribe-Post` for RFC 8058 one-click support.

Rspamd provides the cheap index. Dovecot remains the source of the original message headers.

Header lookups are remembered per Message-ID so old messages are not queried again on every polling cycle. A scan performs at most 50 new Dovecot header lookups; additional historical candidates are picked up by later scans.

## Stored data

Newsletter metadata is stored in the SQLite database configured with `MOOLIAS_NEWSLETTER_DB_PATH`.

Moolias stores:

- mailbox and receiving alias
- stable sender identity
- display name and sender address
- optional List-ID
- first and last observation time
- observed message count
- latest Message-ID
- unsubscribe state
- up to the three newest different HTTPS unsubscribe URLs
- optional `mailto:` target associated with a stored HTTPS URL
- whether a stored URL qualified for verified one-click handling

Unsubscribe URLs are stored in plaintext. This is intentional: the same personalized URLs already arrive as plaintext mail headers and may still be present in the Mailcow message store. Moolias does not write complete unsubscribe URLs to normal application logs.

When a fourth different URL is learned for the same newsletter, the oldest stored URL is removed.

The newsletter database is separate from the local mailbox-preference/state database configured by `MOOLIAS_USAGE_DB_PATH`. Both files must live on persistent storage under normal Docker deployments.

## One-click unsubscribe

Moolias distinguishes two types of HTTPS unsubscribe mechanism.

### RFC 8058 one-click

A URL is treated as one-click only when:

- `List-Unsubscribe-Post` declares `List-Unsubscribe=One-Click`
- Rspamd recorded a successful DKIM result
- the message's DKIM signature declares both `List-Unsubscribe` and `List-Unsubscribe-Post` in its signed-header list

After explicit user confirmation, the Moolias backend sends the RFC 8058 POST. If the newest stored one-click URL fails, Moolias can try the remaining stored one-click URLs from newest to oldest.

### Normal HTTPS unsubscribe page

When an HTTPS URL exists without verified one-click support, Moolias opens the newest URL in the user's browser. Moolias does not attempt to automate arbitrary unsubscribe forms.

## SSRF protection

RFC 8058 requires a server-side request to a URL supplied by an incoming email, so Moolias treats that URL as untrusted input.

For one-click requests Moolias:

- permits HTTPS only
- permits port 443 only
- rejects URLs containing credentials or control characters
- resolves the hostname before connecting
- rejects the request if any resolved address is non-public, including loopback, private, link-local and Docker/internal addresses
- connects to the validated IP address while retaining the original hostname for TLS SNI and certificate verification
- does not follow HTTP redirects
- sends no browser cookies or authentication headers
- limits connection/read time and response-header size

Normal non-one-click unsubscribe pages are opened by the user's browser instead.

## Restricted Newsletter Agent

The Moolias web application does not receive the Dovecot `doveadm_password` and does not mount the Mailcow mail volume or Docker socket.

`scripts/install-newsletter-agent.sh` installs a dedicated sidecar on the Mailcow network. It:

- runs as uid 10001
- has a read-only root filesystem
- has no host mounts
- has no published host ports
- drops all Linux capabilities
- exposes only the signed `/v1/headers` API through Mailcow nginx
- accepts only a mailbox and exact Message-ID
- returns only the fixed newsletter-related header set

The web application authenticates requests to the agent with a separate HMAC secret.

## Configuration

```dotenv
# Global administrator switch. Mailboxes can opt in only while this is true.
MOOLIAS_NEWSLETTER_MANAGEMENT=true

# Newsletter observations and unsubscribe metadata.
MOOLIAS_NEWSLETTER_DB_PATH=/data/moolias-newsletters.sqlite3

MOOLIAS_NEWSLETTER_AGENT_SECRET=<generated-secret>
MOOLIAS_NEWSLETTER_AGENT_URL=
MOOLIAS_NEWSLETTER_POLL_SECONDS=60
MOOLIAS_NEWSLETTER_HISTORY_COUNT=1000

# Persistent Moolias mailbox/UI state. Required even with statistics disabled.
MOOLIAS_USAGE_DB_PATH=/data/moolias-stats.sqlite3
```

The recommended installer creates the agent secret, configures Dovecot remote `doveadm` authentication when necessary, adds the sidecar to Mailcow's Compose override and enables the server-side feature in the Moolias `.env`. Individual mailboxes are still asked for their own choice in Moolias.

Run it on the Mailcow host with:

```bash
cd /opt/moolias
sudo bash scripts/install-newsletter-agent.sh
```

The script intentionally requires root because it modifies Mailcow configuration files and restarts/reloads Mailcow services. The script is idempotent for its managed Dovecot, nginx and Compose blocks. If an administrator already configured `doveadm_password`, the installer reuses that setting rather than replacing it.

After installation, restart or rebuild the Moolias application so the new application settings and image are active.
