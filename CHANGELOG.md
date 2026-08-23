# Changelog

All notable changes to Moolias are documented here.

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
