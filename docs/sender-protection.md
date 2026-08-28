# Mailcow Agent and optional primary sender protection

Moolias uses one hardened Mailcow Agent for two separate responsibilities:

1. **Required alias-workflow delivery bypass:** guided alias creation and replacement temporarily bypass greylisting for the exact new recipient address (and, during replacement, the old address as well). The Agent owns the recipient map and expiry state on the Mailcow host.
2. **Optional primary sender protection:** when enabled by the administrator, Moolias can prevent a signed-in mailbox user from sending with the mailbox's primary address while normal aliases continue through Mailcow's standard sender policy.

The Agent itself is required for guided alias creation and replacement. Primary sender protection remains disabled by default and can be switched on independently with `MOOLIAS_SENDER_PROTECTION=true`.

## First-mail delivery bypass

For a new alias, Moolias asks the Agent to add only that exact recipient address to a short-lived Rspamd map. For a replacement, both the old and new recipient addresses are added while the confirmation phase is active.

The managed map lives at:

```text
data/conf/rspamd/custom/moolias-agent/moolias_firstmail_recipients.map
```

The installed Rspamd pre-filter checks the SMTP recipient and, only for a single exact recipient present in that map, disables the normal greylisting symbols:

```text
GREYLIST_CHECK
GREYLIST_SAVE
```

It does not disable spam filtering, antivirus checks or other Rspamd policy. The browser never controls this rule directly and the GUI does not expose Rspamd/greylisting implementation details.

Bypass expiry is persisted in the Agent's private state. The Agent removes expired entries independently of an active browser session and reconstructs the map from state on startup. Moolias can also remove the bypass early when the expected first delivery has been detected.

The maximum workflow bypass lifetime is configured in the Moolias application with:

```dotenv
MOOLIAS_ALIAS_WORKFLOW_BYPASS_SECONDS=900
```

## Primary sender protection

Mailcow's normal authenticated sender policy remains in place. When primary sender protection is enabled, Moolias adds one small PCRE sender-login map before Mailcow's normal SQL map:

```text
pcre:/opt/postfix/conf/moolias-agent/blocked_sender_login.pcre
proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

The Moolias policy file lives inside Mailcow's existing Postfix configuration tree:

```text
data/conf/postfix/moolias-agent/blocked_sender_login.pcre
```

Postfix already receives `data/conf/postfix/` through Mailcow's normal configuration mount, so Moolias does not add another volume to `postfix-mailcow`.

For a blocked mailbox the Moolias map returns a deliberately non-existent owner. Mailcow's existing `reject_authenticated_sender_login_mismatch` policy then rejects the primary address as an authenticated sender. Normal Mailcow aliases and sender permissions continue through the SQL map.

The Agent keeps private state separately:

```text
data/conf/moolias-agent/state/state.json
```

Postfix PCRE maps are cached by an `smtpd` worker once opened. The installer therefore adds a small Mailcow Postfix hook that sets `max_use=1` only on authenticated submission services (`smtps`, `10465`, `submission`, `10587`, and SOGo's internal port `588`, when those services exist). Each new client connection consequently uses a fresh `smtpd` process and sees the current policy file. Normal SMTP delivery services are not changed.

The installation restarts `postfix-mailcow` once so Postfix consumes the persistent configuration and hook. Runtime sender-protection switch changes do not reload, restart or recreate Postfix.

## Existing sender-login PCRE rules

An administrator may already have a manual map such as:

```text
data/conf/postfix/blocked_sender_login.pcre
```

The installer does not silently take ownership of that file. If it is already active in `smtpd_sender_login_maps`, the existing map remains separate from the Moolias map:

```text
pcre:/opt/postfix/conf/blocked_sender_login.pcre
pcre:/opt/postfix/conf/moolias-agent/blocked_sender_login.pcre
proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

Simple exact-address rules are shown during interactive installation. The administrator can explicitly choose whether those exact rules should move under Moolias management.

If they are imported:

- only the recognized exact-address lines are removed from the old file;
- the addresses are added to the Moolias Agent state;
- the Moolias policy renders them with the Moolias blocked-owner marker;
- unrelated comments, custom rules and regular expressions remain untouched.

If they are not imported, the old rules stay under the existing Postfix policy. Moolias records the recognized exact addresses as externally managed and shows the sender-protection switch as read-only for those users instead of pretending that the address can be unblocked through Moolias.

Rules that cannot be mapped safely to one exact mailbox address are never imported automatically.

For unattended installation the prompt can be controlled explicitly:

```bash
MOOLIAS_IMPORT_EXISTING_SENDER_RULES=yes sudo bash install-mailcow-agent.sh
MOOLIAS_IMPORT_EXISTING_SENDER_RULES=no sudo bash install-mailcow-agent.sh
```

The default is `ask`. When no interactive terminal is available, existing rules are kept external unless an explicit `yes` was supplied.

## Security model

Moolias-to-Agent requests are authenticated with HMAC-SHA256 using `MOOLIAS_MAILCOW_AGENT_SECRET`, which is never exposed to the browser. Signed requests include a timestamp and nonce. The Agent rejects invalid signatures, stale requests and nonce replays.

For primary sender protection, the browser sends only the desired boolean state. Moolias derives the mailbox from the authenticated server-side session, validates ownership and CSRF, and then contacts the Agent. Clients cannot submit arbitrary mailbox policy or PCRE rules.

For delivery bypass, recipients come from aliases that Moolias has already created/validated server-side. The Agent independently normalizes and validates addresses before updating its map.

The Agent:

- runs explicitly as uid/gid `10001:10001`;
- has no SSH access;
- has no Docker socket;
- has no Mailcow API key or database credentials;
- runs without Linux capabilities, with `no-new-privileges`, and with a read-only root filesystem;
- has no host port published directly;
- can write only its private state directory, dedicated Postfix policy directory and dedicated Rspamd recipient-map directory;
- validates and escapes mailbox addresses itself;
- serializes state changes with a file lock;
- enforces a per-mailbox sender-protection cooldown, 10 seconds by default.

Its only writable mounts are:

```text
/state
/postfix-policy
/rspamd-custom
```

The SMTP sender-policy path has no runtime dependency on Agent availability. If the Agent stops, the last rendered Postfix policy remains on disk and existing sender protection continues to be enforced. Changes to sender protection and alias-workflow bypass state are unavailable until the Agent returns.

The Agent has no published host port. For a standalone Moolias application on another host, the installer also exposes the authenticated Agent API through Mailcow nginx at `/moolias-agent/`; that location limits request bodies to 4 KiB and state-changing endpoints still require a valid HMAC signature. The recommended same-host Moolias application bypasses nginx and connects directly to `http://moolias-agent:8081` on the Mailcow Docker network.

## Installation

For the recommended same-host deployment, do **not** install the Agent separately. The normal Moolias installer installs or updates it automatically, stores the shared secret in `/opt/moolias/.env`, configures `MOOLIAS_MAILCOW_AGENT_URL=http://moolias-agent:8081` for direct Docker-network access and validates the Agent before completing:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/install.sh \
  | sudo bash
```

The setup question about primary sender protection controls only whether `MOOLIAS_SENDER_PROTECTION` is enabled. The Agent is installed either way because alias workflows require it.

For a standalone Moolias application running on another host, install the Agent manually on the **Mailcow host**. For the stable image channel:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install-mailcow-agent.sh \
  | sudo env MOOLIAS_AGENT_IMAGE=ghcr.io/vain90/moolias:latest bash
```

The child installer defaults to the `edge` image for development/integration use. Production standalone installations should explicitly select the same stable/pinned Moolias image channel used by the application.

The installer assumes Mailcow is located at `/opt/mailcow-dockerized`. For another location, preserve `MAILCOW_DIR` explicitly, for example:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install-mailcow-agent.sh \
  | sudo env \
      MAILCOW_DIR=/path/to/mailcow \
      MOOLIAS_AGENT_IMAGE=ghcr.io/vain90/moolias:latest \
      bash
```

For administrators who prefer to inspect the script before running it:

```bash
curl -fsSLO \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install-mailcow-agent.sh
less install-mailcow-agent.sh
sudo env MOOLIAS_AGENT_IMAGE=ghcr.io/vain90/moolias:latest bash install-mailcow-agent.sh
```

The Agent installer:

1. validates the Mailcow directory and Docker Compose;
2. detects the previous published `moolias-sender-agent` layout and compatible sender maps;
3. preserves/migrates the previous Agent secret and version-1 sender state when present;
4. inspects any separate administrator sender-login PCRE configuration;
5. optionally imports recognized exact existing sender rules after explicit approval;
6. creates private state under `data/conf/moolias-agent/state/`;
7. creates the dedicated Postfix policy under `data/conf/postfix/moolias-agent/`;
8. creates the exact-recipient bypass map under `data/conf/rspamd/custom/moolias-agent/`;
9. installs the Postfix and Rspamd hooks/configuration required for those dedicated maps;
10. replaces only its marked old/current Agent Compose block with the `moolias-agent` service;
11. adds `/moolias-agent/` to Mailcow nginx;
12. validates the combined Compose and Rspamd configuration;
13. starts and hardening-checks the new Agent;
14. removes the previous managed nginx location before validating/reloading nginx;
15. restarts and validates Postfix and Rspamd so both managed maps are active;
16. only after successful validation retires the previous running `moolias-sender-agent` container and archives its old state/policy directories;
17. prints `MOOLIAS_MAILCOW_AGENT_SECRET` for standalone/manual application configuration.

Existing Compose services outside Moolias-managed blocks are preserved. If existing YAML, nginx, Postfix or Rspamd configuration cannot be merged conservatively, the installer stops rather than claiming ownership of administrator configuration.

## Configure Moolias manually

The required shared secret is:

```dotenv
MOOLIAS_MAILCOW_AGENT_SECRET=replace-with-the-secret-printed-by-the-installer
```

For a standalone Moolias application, an empty Agent URL uses:

```text
<MAILCOW_URL>/moolias-agent
```

Only set a custom URL when the Agent is reachable elsewhere:

```dotenv
MOOLIAS_MAILCOW_AGENT_URL=https://mail.example.org/moolias-agent
```

For the recommended same-host deployment, the normal installer instead writes the direct Docker-network URL automatically:

```dotenv
MOOLIAS_MAILCOW_AGENT_URL=http://moolias-agent:8081
```

Primary sender protection is controlled separately:

```dotenv
MOOLIAS_SENDER_PROTECTION=false
```

Enable it when desired:

```dotenv
MOOLIAS_SENDER_PROTECTION=true
MOOLIAS_SENDER_PROTECTION_COOLDOWN_SECONDS=10
```

When `MOOLIAS_SENDER_PROTECTION=false`, Moolias does not use the Agent's primary-sender-protection endpoints, but it still uses the required Agent for guided alias creation/replacement delivery bypasses.

Restart the Moolias application after changing its `.env` file.

## Updating and migrating the Agent

Re-running the current installer reuses the current Agent secret and state, replaces only Moolias-managed configuration, validates the result and restarts the Agent as required. Administrator configuration outside managed blocks is left alone.

Published v1.2.1 installations used the earlier names:

```text
moolias-sender-agent
data/conf/moolias-sender-agent/
data/conf/postfix/moolias-sender-agent/
data/conf/nginx/site.moolias-sender-agent.custom
```

The current installer recognizes that layout. It copies the existing secret and version-1 state into the unified `moolias-agent` layout, accepts the old sender-map path during migration, validates the replacement Agent/Postfix/Rspamd/nginx configuration, then removes the old running container and archives the old private state/policy directories with timestamped `.before-moolias-agent-*.bak` names.

If the previous layout exists but its private state or secret is missing, the installer fails closed instead of generating a replacement secret or silently discarding sender-protection state.
