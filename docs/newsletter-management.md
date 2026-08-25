# Newsletter management

Moolias can detect newsletter and mailing-list messages from Mailcow's Rspamd history and expose a compact unsubscribe view for each Moolias mailbox.

The feature is disabled by default and has two independent enablement levels:

1. An administrator makes newsletter management available server-wide with `MOOLIAS_NEWSLETTER_MANAGEMENT=true` and installs the restricted Newsletter Agent.
2. Mailcow tags on the domain and/or mailbox decide whether newsletter management is enabled for a particular mailbox.

The effective state is therefore **server enabled AND effective Mailcow newsletter policy enabled**.

## Domain and mailbox policy

Newsletter enablement intentionally follows the same inheritance model as Moolias usage statistics.

With the default base tag `moolias-newsletter`:

- `moolias-newsletter` = enabled
- `moolias-newsletter-off` = disabled

A mailbox tag overrides the domain tag. If the mailbox has neither newsletter tag, it inherits the domain setting. If neither the mailbox nor the domain has a matching tag, the safe default is off.

Examples:

| Domain tags | Mailbox tags | Effective state |
| --- | --- | --- |
| `moolias-newsletter` | none | enabled by domain |
| `moolias-newsletter` | `moolias-newsletter-off` | disabled by mailbox override |
| `moolias-newsletter-off` | `moolias-newsletter` | enabled by mailbox override |
| none | none | disabled |

Moolias users may change only this newsletter tag family for their own mailbox through Settings. Unrelated Mailcow tags are preserved. The choices are the same style as statistics: **Use domain setting**, **Off**, or **On**.

Conflicting tags at the active policy level fail closed. For example, if a mailbox contains both `moolias-newsletter` and `moolias-newsletter-off`, Moolias reports a tag conflict and treats newsletter management as disabled until the conflict is corrected.

If the administrator sets `MOOLIAS_NEWSLETTER_MANAGEMENT=false`, newsletter management is disabled regardless of tags. The mailbox control is shown disabled/greyed with a server-side-disabled explanation. Existing Mailcow newsletter tags and already stored newsletter data are not removed.

There is no additional opt-in prompt at login.

## Enabling and historical data

When a settings change makes the **effective** newsletter state switch from off to on, Moolias asks whether the still-available historical data should also be evaluated.

The user can choose:

- **Include history**: Moolias may process matching entries that are still present in the configured Rspamd history window and recover their newsletter metadata from original messages still available in Dovecot.
- **Detect from now on only**: Moolias records a mailbox-specific scan watermark and ignores Rspamd entries older than the activation time.

This question is tied to an actual effective off-to-on transition. It is not shown merely because the source of the setting changes. For example, switching from an explicit mailbox `On` override to an inherited domain `On` value remains effectively enabled and therefore does not ask again.

If newsletter management is later disabled and then enabled again, the question is shown again for that new off-to-on transition. Choosing **Detect from now on only** replaces the previous watermark with the new activation time. Choosing **Include history** opens the watermark to all history that is still available at that point.

If an administrator enables newsletter tags directly in Mailcow without an interactive Moolias settings change, Moolias defaults to **from now on** rather than silently importing historical messages.

The history watermark is operational collector state stored in `MOOLIAS_NEWSLETTER_DB_PATH`; it is not the source of the user's enable/disable preference. Mailcow tags remain the only newsletter policy source.

## User experience

The Newsletter page shows one compact row per detected sender and recipient alias. The row includes the sender, the alias that received the message, the observed message count, the most recent message and the available unsubscribe action.

The Newsletter navigation entry is shown only when the feature is effectively enabled for the signed-in mailbox. When it is disabled by the mailbox/domain policy, the setting can be changed from Settings if the administrator has enabled the feature server-wide.

The table supports search, active/unsubscribed filtering and pagination. The details control expands technical information only when it is needed.

A detected sender remains visible even when Moolias cannot recover a usable HTTPS unsubscribe URL. In that case the direct unsubscribe button is disabled. This can happen when the original message has already been deleted from Dovecot.

Successfully accepted RFC 8058 one-click unsubscribes remain visible as unsubscribed entries. If a newer message from that subscription is observed afterwards, Moolias highlights the row as mail received after unsubscribe instead of silently forgetting the previous unsubscribe state.

## Additional forwarding addresses and linked mailboxes

Newsletter Management can optionally include receiving addresses that are not normal owned Moolias aliases. There are two supported sources.

### Direct Mailcow alias forwards

A Mailcow alias qualifies automatically when it is active, is not a catch-all, has exactly one `goto` target, points directly at the authenticated mailbox, and is not already a normal owned Moolias alias. Shared aliases, catch-alls and forwarding chains are deliberately excluded.

### Explicitly linked Mailcow mailboxes

For old addresses that still exist as real Mailcow mailboxes and are forwarded by an administrator through Sieve or another routing mechanism, Moolias does **not** inspect or parse the routing rule. Instead, the administrator explicitly links source and target mailboxes with Mailcow mailbox tags.

With the default newsletter base tag, a link named `private` is configured as follows:

```text
Target/main mailbox:
  moolias-newsletter-link-private-target

Old/source mailbox:
  moolias-newsletter-link-private-source
```

The part between `link-` and `-source`/`-target` is the link ID. It may contain lowercase letters, digits, dots, underscores and hyphens and may be chosen freely. Multiple old mailboxes can use the same source tag to link them to one target mailbox. A target mailbox may also carry multiple target link IDs.

For a custom `MOOLIAS_NEWSLETTER_TAG`, the same pattern derives from that base tag. For example, `MOOLIAS_NEWSLETTER_TAG=company-news` produces `company-news-link-private-target` and `company-news-link-private-source`.

Only active Mailcow mailboxes with a source tag matching a target tag on the authenticated mailbox qualify. The tags express the administrative relationship only: Moolias does not create, verify or change the actual Sieve/forwarding configuration.

Moolias reads Mailcow's mailbox list at most once per authenticated browser session when the user first opens the Newsletter page or first uses the forwarding control. The resolved source addresses are cached in the running Moolias process for that target mailbox. The background collector does **not** call `mailbox/all` or inspect Sieve filters on every polling cycle. Repeated page reloads and the normal Newsletter refresh action reuse the session/process cache. After a new login session the links are evaluated again; after an application restart they are also reloaded even if the browser session cookie still exists.

When at least one qualifying direct forwarding alias or explicitly linked source mailbox exists, the Newsletter page shows an **Include forwarded addresses** control. If none exist, no forwarding control is rendered. Enabling the option stores the derived mailbox tag `moolias-newsletter-forwarded` when the default newsletter base tag is used. With a custom base tag, the forwarding flag is `<base-tag>-forwarded`.

This forwarding flag is mailbox-only and has no domain inheritance. It does not change any Mailcow alias, mailbox, Sieve script or routing configuration.

The existing newsletter-history watermark is still respected. Enabling forwarded addresses does not override an earlier **Detect from now on only** decision. If the mailbox was configured to include available history, matching Rspamd entries for a qualifying forwarded address may be imported while they remain available.

Newsletter rows received through such an address show the configured Mailcow alias/mailbox display name when available, the receiving email address, and a **Forwarded** marker.

## Discovery flow

Moolias uses Rspamd as a cheap candidate index so it does not have to read the body of every stored message.

1. Moolias reads the configured Rspamd history window through the existing Mailcow API integration.
2. Standard candidates are messages for which Rspamd recorded `MAILLIST` or `HAS_LIST_UNSUB`.
3. The Moolias Mailcow installer additionally installs a zero-score Rspamd Lua detector. It records `MOOLIAS_BODY_UNSUB` when a message body contains a likely unsubscribe action such as `unsubscribe`, `Abbestellen`, `Abmelden`, `opt out` or `manage preferences` and the message contains URLs. The Rspamd symbol contains only the matched indicator and **never the personalized unsubscribe URL**.
4. A candidate must also have been accepted without a spam action and carry an authentication signal such as DKIM or DMARC allow. Rspamd history may expose symbols either as structured data or as scored strings such as `MAILLIST(-0.18)[generic]`; Moolias normalises both forms.
5. Moolias associates the Rspamd SMTP recipient with the authenticated user's mailbox, one of that user's normal Mailcow aliases, or an explicitly opted-in forwarding/linked address.
6. The mailbox history watermark is applied before historical observations or message lookups are stored.
7. For normal `MAILLIST`/`HAS_LIST_UNSUB` candidates, the restricted Newsletter Agent asks Dovecot for a fixed set of headers for the exact target mailbox and Message-ID.
8. Only for `MOOLIAS_BODY_UNSUB` candidates may the agent additionally request the UTF-8 message text for that exact Message-ID. It searches locally for a nearby HTTPS unsubscribe link and returns only the extracted URL to the Moolias application; the message body itself is not returned or stored by Moolias.
9. Header-based HTTPS and `mailto:` targets come from `List-Unsubscribe`. `List-Unsubscribe-Post` and DKIM coverage determine whether a header-based HTTPS URL qualifies for RFC 8058 one-click handling. A body-derived URL is always treated as a normal unsubscribe page, never as RFC 8058 one-click.

This two-stage design catches providers such as Sonos that put an unsubscribe link only in the footer while avoiding broad IMAP/Dovecot body scans for ordinary mail.

Header/body lookups are remembered per Message-ID so old messages are not queried again on every polling cycle. A scan performs at most 50 new Dovecot lookups; additional historical candidates are picked up by later scans.

### Historical limitation of the body detector

`MOOLIAS_BODY_UNSUB` is added by Rspamd while a message is scanned. Installing the detector does not retroactively add the symbol to entries that are already present in Rspamd history. Existing historical messages without `MAILLIST`/`HAS_LIST_UNSUB` therefore do not automatically become body-only candidates merely because the plugin is installed. New matching messages are detected from that point onward.

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
- the operational history watermark used for historical import/from-now behavior

Unsubscribe URLs are stored in plaintext. This is intentional: the same personalized URLs already arrive as plaintext mail headers or message content and may still be present in the Mailcow message store. Moolias does not write complete unsubscribe URLs to normal application logs.

When a fourth different URL is learned for the same newsletter, the oldest stored URL is removed.

The newsletter policy and forwarded-address opt-in are not stored in SQLite. Mailcow domain/mailbox tags are the source of truth for enablement and linked-mailbox relationships.

## One-click unsubscribe

Moolias distinguishes two types of HTTPS unsubscribe mechanism.

### RFC 8058 one-click

A URL is treated as one-click only when:

- `List-Unsubscribe-Post` declares `List-Unsubscribe=One-Click`
- Rspamd recorded a successful DKIM result
- the message's DKIM signature declares both `List-Unsubscribe` and `List-Unsubscribe-Post` in its signed-header list

After explicit user confirmation, the Moolias backend sends the RFC 8058 POST. If the newest stored one-click URL fails, Moolias can try the remaining stored one-click URLs from newest to oldest.

Moolias marks the newsletter as unsubscribed only after the provider accepts the POST with a 2xx HTTP response.

### Normal HTTPS unsubscribe page

When an HTTPS URL exists without verified one-click support, including URLs recovered from the message body, Moolias opens the newest URL in the user's browser. Moolias does not attempt to automate arbitrary unsubscribe forms and cannot know whether the user completed the action on the provider's page.

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
- normally returns only the fixed newsletter-related header set
- may inspect the UTF-8 message text only when Moolias explicitly marks the request as a Rspamd `MOOLIAS_BODY_UNSUB` candidate
- returns only a matched HTTPS unsubscribe URL from such a body lookup, not the body itself

The web application authenticates requests to the agent with a separate HMAC secret.

## Mailcow Rspamd detector

The same installer also installs `scripts/rspamd/moolias_newsletter.lua` into Mailcow's persistent Rspamd configuration and enables it through a managed block in `data/conf/rspamd/rspamd.conf.local`.

The installer runs `rspamadm configtest` before accepting the Rspamd change. If Rspamd rejects the configuration, the previous plugin/configuration files are restored. On success the Rspamd container is restarted so new incoming messages can receive `MOOLIAS_BODY_UNSUB`.

The detector has score `0.0`; it is a classification hint for Moolias and does not make a message more or less spammy.

## Configuration

```dotenv
# Global administrator switch.
MOOLIAS_NEWSLETTER_MANAGEMENT=true

# Domain/mailbox policy tag family. Additional mailbox tags derive from this base:
# <base>-forwarded
# <base>-link-<id>-target
# <base>-link-<id>-source
MOOLIAS_NEWSLETTER_TAG=moolias-newsletter

# Newsletter observations, unsubscribe metadata and history watermark.
MOOLIAS_NEWSLETTER_DB_PATH=/data/moolias-newsletters.sqlite3

MOOLIAS_NEWSLETTER_AGENT_SECRET=<generated-secret>
MOOLIAS_NEWSLETTER_AGENT_URL=
MOOLIAS_NEWSLETTER_POLL_SECONDS=60
MOOLIAS_NEWSLETTER_HISTORY_COUNT=1000
```

The recommended installer creates the agent secret, configures Dovecot remote `doveadm` authentication when necessary, installs the Rspamd body detector, adds the sidecar to Mailcow's Compose override and enables the server-side feature in the Moolias `.env`. The domain/mailbox Mailcow tags then determine which mailboxes actually use newsletter management.

Run it on the Mailcow host with:

```bash
cd /opt/moolias
sudo bash scripts/install-newsletter-agent.sh
```

The script intentionally requires root because it modifies Mailcow configuration files and restarts/reloads Mailcow services. The script is idempotent for its managed Dovecot, nginx, Compose and Rspamd blocks. If an administrator already configured `doveadm_password`, the installer reuses that setting rather than replacing it.

After installation, restart or rebuild the Moolias application so the new application settings and image are active.
