# Changelog

All notable changes to Moolias are documented here.

## 1.1.6 - 2026-08-24

### Fixed

- Mailcow ACME is now recreated after `ADDITIONAL_SAN` changes so the running `acme-mailcow` container receives the new SAN list instead of keeping stale environment values
- the dedicated Moolias nginx virtual host now serves Mailcow's `/.well-known/acme-challenge/` path directly from `/web` and keeps HTTPS redirect logic out of that challenge location, allowing HTTP-01 validation for the Moolias hostname
- the guided bootstrap now preserves the TLS check result across the progress-spinner subprocess so the final summary reports `OK`, `PENDING`, external/manual or not-required instead of incorrectly falling back to `not checked`

## 1.1.5 - 2026-08-24

### Fixed

- the terminal progress spinner now keeps every animation frame exactly one character wide, so status text no longer shifts when the backslash frame is rendered
- the same-host Mailcow installer now includes both IPv4 and IPv6 CIDRs from the detected Mailcow Docker network in API allowlist guidance and validation errors, so dual-stack installations no longer suggest only the IPv4 subnet

## 1.1.4 - 2026-08-23

### Changed

- the recommended Mailcow-host installer now presents fresh installations as a six-step terminal setup wizard with one focused page at a time for URL, API, OAuth, access control, TLS and sender protection
- fresh same-host installations recommend the `moolias-access` Mailcow tag and write `MOOLIAS_ACCESS_TAG=moolias-access` unless the operator opts out or supplies an explicit value
- primary sender protection is now the recommended choice in the public setup flow and uses `Yes` as the default answer
- long-running install, Mailcow/ACME, final configuration, API validation and TLS checks show active progress instead of leaving the terminal apparently idle
- normal installer reruns preserve an existing enabled or disabled sender-protection choice unless the operator explicitly requests a change

### Fixed

- Mailcow API validation now preserves Mailcow's rejection reason, distinguishing an invalid API key from a source-IP allowlist failure and exposing the source IP reported by Mailcow when available

## 1.1.3 - 2026-08-23

### Changed

- the public Mailcow bootstrap now recognizes an already enabled sender-protection setup during a repair/rerun and preserves it without asking the child installer to install the sidecar again
- failure output filters routine successful nginx warnings and validation chatter while retaining actual nginx errors and the real installer failure
- the disposable-Mailcow integration test now runs the public installer a second time against the same persisted installation with sender protection already enabled

### Fixed

- rerunning the public installer on an installation with `MOOLIAS_SENDER_PROTECTION=true` no longer fails with `MOOLIAS_INSTALL_SENDER_PROTECTION must be ask, yes or no`

## 1.1.2 - 2026-08-23

### Changed

- the recommended Mailcow-host bootstrap now keeps the public Mailcow URL separate from a dedicated internal backend URL instead of overriding `MAILCOW_URL` inside Compose
- the internal Mailcow URL is derived from the real `HTTP_PORT` in `mailcow.conf` rather than assuming the disposable-CI port `8080`
- the public installer now suppresses successful nested installer summaries and routine stderr noise, then prints one concise final status after validation
- sender-protection secrets created by the integrated installer are stored automatically in `/opt/moolias/.env` and are no longer presented as a copy/paste step in the final user-facing flow
- the bootstrap waits briefly for a Mailcow ACME certificate containing the Moolias hostname and reports TLS as `OK` or `PENDING` explicitly

### Fixed

- same-host installations using Mailcow's normal `HTTP_PORT=80` no longer fail their post-install API validation with `Connection refused`
- Mailcow API calls and server-side OAuth token/profile requests can use `MAILCOW_INTERNAL_URL`, while browser-facing OAuth authorization continues to use the public `MAILCOW_URL`
- the installer no longer announces a successful installation before its API and TLS checks have completed

## 1.1.1 - 2026-08-23

### Changed

- the public Mailcow-host installer now detects the actual Mailcow Docker-network IPv4 CIDR and tells the administrator exactly what to allow for the Moolias read/write API key before asking for the key
- the recommended same-host installation explicitly keeps Mailcow's API IP check enabled and avoids allowlisting a single disposable Moolias container address
- the Mailcow-host installation guide now documents the API allowlist requirement and uses the stable-aware public bootstrap command

### Fixed

- the public bootstrap now validates a read-only Mailcow API request from inside the running Moolias container after installation so an invalid API key or source-IP/CIDR allowlist fails with a clear diagnostic instead of surfacing later in the application

## 1.1.0 - 2026-08-23

### Added

- guided `scripts/install.sh` for the recommended same-host Mailcow deployment under `/opt/moolias`
- stable-aware root `install.sh` bootstrap that prefers the latest release and safely bridges the first installer release from `main`
- dedicated `compose.mailcow.yml` that joins Mailcow's existing Docker network without publishing another host port
- automatic Mailcow Docker-network discovery from the running `nginx-mailcow` service
- installer-managed Mailcow nginx virtual host with validation, backups and support for Mailcow ACME or external TLS
- optional hand-off from the main installer to the hardened primary-sender-protection sidecar installer
- real disposable-Mailcow integration coverage for the recommended installation path

### Changed

- the README now recommends the separate same-host Mailcow Compose deployment for most installations while retaining standalone Docker as a supported alternative
- deployment security documentation now describes the same-host network boundary and explicitly excludes Docker socket, Mailcow database and Mailcow configuration mounts from the main application

## 1.0.1 - 2026-08-23

### Changed

- the authenticated header now uses the same 8 px spacing between the language selector and Settings as between Settings and Help
- the Overview `Recently used` list now shows the assigned alias name first and the alias address underneath
- the repository's explicit local-development Compose file is now named `compose.dev.yml`, leaving `compose.local.yml` available for operator-specific deployment overrides

### Fixed

- the updater now ignores the legacy stock development `compose.local.yml` from older clones instead of accidentally layering `moolias:local` over the stable GHCR image

## 1.0.0 - 2026-08-23

### Added

- redesigned application shell with dedicated Overview, Aliases, Offline Pool and Statistics views
- overview dashboard with actionable status cards, recent aliases and an in-place `Action required` / `Handlungsbedarf` workflow
- locally bundled Lucide UI icons throughout navigation, settings, cards and actions, including `chart-no-axes-combined` for statistics
- new Moolias masked-mail branding with favicon, Apple touch icon and installable web-app assets for Apple, Android, Windows and other PWA-capable platforms
- Mailcow-style language dropdown for the currently supported German and English interfaces, using native language names and locally rendered flags
- compact offline-pool creation menu with `+1`, `+5` and `+10`
- account popover with Mailcow alias quota and the number of aliases managed by Moolias
- statistics overview with received/sent usage, recognition rate, active aliases, automatically detected senders and review data according to the selected privacy mode
- optional backfill of available Mailcow/Rspamd history when increasing the statistics privacy/detail level
- visible processing states while historical statistics are evaluated and while privacy downgrades remove or collapse stored details
- Rspamd spam verdict safety brake for automatic sender recognition, while preserving explicit manual user decisions
- targeted automatic recognition for short known brands such as ING and dm without relaxing the general conservative sender matcher
- local service-logo support with manual per-alias override and a neutral fallback

### Changed

- successful OAuth login now opens the Overview instead of the Aliases page; the configured Mailcow redirect URI remains `/oauth/callback`
- automatic action-required review opens on the Overview without navigating users away from it
- appearance selection moved from the header into Settings
- statistics-mode downgrades now require an explicit in-app confirmation before stored detail is reduced or deleted
- the Mailcow alias quota indicator uses a CSP-compatible semantic meter instead of blocked inline width styling
- offline-pool creation no longer offers batches of 20 aliases
- UI controls, status cards and navigation use a consistent professional icon language instead of text-symbol placeholders
- language selection is right-aligned in the authenticated header and shows only the active flag until opened

### Fixed

- Mailcow quota bars now reflect the actual used/limit ratio instead of appearing completely filled
- statistics-mode changes now provide immediate visual feedback during potentially slow history evaluation, mode reduction and cleanup
- action-required data loading now provides immediate feedback rather than making the page appear unresponsive
- spacing between alias usage summaries and the unused-alias action is restored
- the new Moolias branding assets are validated as real PNG/WebP files so broken binary assets cannot silently render as blank icons

## 0.2.0 - 2026-08-21

### Breaking changes

- The project has been renamed to Moolias across the Python package, container image, Docker Compose service, runtime identifiers and application configuration. Existing 0.1.x installations must follow `docs/migration-to-moolias.md` before switching to the 0.2.0 stable image.
- application settings now use `MOOLIAS_*`, the container image is `ghcr.io/vain90/moolias`, the Compose service is `moolias`, and the default access/statistics tags and statistics database path use the `moolias` name. Legacy reserved offline-alias markers remain recognized so existing aliases can be migrated safely.

### Added

- unified `Action required` / `Handlungsbedarf` workflow for used offline aliases, unexpected senders and actionable collector-health warnings
- alias replacement directly from the aggregate unexpected-sender review while preserving the existing safe replacement backend
- reusable application-owned confirmation, warning and recoverable-error dialogs instead of native browser dialogs
- collector-health diagnostics for successful/failed polls, staleness, Rspamd history coverage, overlap/headroom and possible gaps
- adaptive Rspamd history loading using `10 -> 25 -> 50 -> 100 -> 250 -> 500 -> configured maximum` with a 10% overlap target
- lightweight three-entry Rspamd history head probe for quiet healthy collectors; unchanged history skips the normal adaptive fetch while changed or uncertain state falls back to the full safety path
- safe long-term pruning of statistics deduplication hashes behind a persistent replay floor and healthy-history watermark
- conservative sender-domain trust using a bundled Public Suffix List snapshot, including separate exact-address/domain decisions in FULL mode and strict compound-brand matching
- Chromium browser E2E coverage for the interactive dashboard and theme behavior
- disposable GitHub-hosted Mailcow feasibility and real Mailcow API integration tests without production credentials or data
- system-aware light/dark appearance selector with `System`, `Light` and `Dark` modes, browser-local persistence and live `prefers-color-scheme` updates
- automated stable release publication after successful `main` CI, including GitHub Release creation and stable multi-architecture GHCR tags

### Changed

- unexpected-sender filtering, counts and pagination are now computed server-side rather than crawling all alias pages in the browser
- disabled aliases no longer contribute to unexpected/action-required alerts while their sender history remains available for traceability
- sender review matching is intentionally stricter around registrable domains, public/private suffixes, subdomains, lookalikes and explicit user decisions
