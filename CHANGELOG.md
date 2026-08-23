# Changelog

All notable changes to Moolias are documented here.

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
- deduplication cleanup runs in bounded batches and only advances after a safely overlapping healthy collector window
- the README has been rewritten around the privacy model, first-time installation and current product behavior rather than implementation history
- the project, documentation, package imports, Compose resources, default tags, cookie names and GHCR image references have been comprehensively moved to the Moolias name

### Fixed

- scrolling inside the aggregate Action required surface no longer gets trapped by nested offline-alias or sender-detail lists
- collector diagnostics no longer confuse the lightweight three-entry unchanged-history probe with a normal loaded history window
- history changes with identical timestamps but different entry identity no longer risk being mistaken for unchanged history

## 0.1.3 - 2026-08-20

### Added

- optional usage-statistics subsystem gated by `MOOLIAS_USAGE_STATS`
- four-level mailcow statistics policy using `moolias-stats-off`, `moolias-stats`, `moolias-stats-domain` and `moolias-stats-full`
- mailbox statistics-mode overrides with domain inheritance and user self-service in the Moolias dashboard
- versioned SQLite storage for alias counters, optional sender aggregates, sender-review state and event deduplication, created only when statistics are enabled
- background collection of accepted incoming alias deliveries and authenticated outgoing alias sends from mailcow Rspamd history
- inline received/sent usage counters and last-used timestamps for opted-in mailboxes
- optional sender-domain or full sender-address aggregation for incoming alias mail
- sender review with manual expected/unexpected decisions and conservative automatic recognition from meaningful alias-purpose/local-part words
- `Unexpected` / `Nicht erwartet` review filter with a global count across assigned aliases
- aggregate `Review all` / `Alle prüfen` workflow for aliases that need sender review, including an automatic once-per-login prompt when review is pending
- per-alias option to disable unexpected-sender review while retaining sender statistics
- sender-detail dialogs for assigned aliases and used offline-pool aliases
- usage detection for reserved offline aliases before assignment, including accepted incoming and authenticated outgoing messages
- once-per-login assignment prompt for used offline-pool aliases
- persistent mailcow lifecycle marker for reserved aliases that have ever been used, independent of retained statistics data
- persistent Docker data volume for deployments that enable statistics

### Changed

- reserved offline aliases that have been used must be assigned before they can enter the normal alias lifecycle; they can no longer be deleted or exported/copied as unused pool addresses
- the offline pool treats both received and sent messages as usage and keeps action buttons aligned when deletion is unavailable
- `FULL -> DOMAIN` privacy downgrades collapse full sender addresses to domain aggregates while preserving allowed counts, latest timestamps and consistent manual review decisions
- downgrades to `BASIC` remove sender-detail aggregates and review decisions; switching to `OFF` additionally removes stored usage counters while the non-statistical used-reserved lifecycle marker remains in mailcow
- statistics-mode changes prevent retroactive collection of older sender detail and stale collector writes after a privacy downgrade
- mailbox statistics tags override domain defaults; conflicting mode tags on the same level pause statistics for safety without unnecessarily destroying stored state
- live search preserves the dynamically added unexpected-sender workflow
- expired or missing browser sessions on protected pages redirect to login, while API/fetch requests continue to receive a JSON `401`
- offline sender details use the same unexpected visual treatment as assigned aliases while review actions remain unavailable until assignment

### Fixed

- mailcow mailbox statistics-tag removal now uses the API's required POST method instead of returning `405 Method Not Allowed`
- `FULL -> DOMAIN` no longer loses sender-domain history
- the unexpected-sender filter no longer disappears after live-search refreshes
- offline-pool sender dialogs remain functional while the unexpected filter is active
- used offline aliases cannot regain a delete path after statistics are switched off
- used offline aliases are excluded from `pool.txt` and `Copy all` even before their persistent lifecycle marker has been written

## 0.1.2 - 2026-08-19

### Added

- optional mailcow tag based access control for individual mailboxes or complete domains

### Changed

- mailboxes without the configured access tag now return to a clear Moolias access-denied screen instead of showing a raw JSON error after OAuth
- active Moolias sessions are revalidated against the configured mailcow access tag on protected alias routes, so removing the tag revokes access on the next request
- improved the assigned-alias layout on small screens
- reduced the visual weight and size of active/SOGo status badges on mobile
- changed the mobile alias edit popover into a viewport-safe bottom sheet with its own scrolling area

## 0.1.1 - 2026-08-19

### Added

- self-updating `update.sh` for deployments following the latest stable release
- explicit `--beta` updater mode for testing the unreleased `edge` image and refreshing the updater from `main`
- automatic health verification after updates with rollback to the previously running image on failure
- `--check`, `--yes`, `--force` and version/help options for the updater
- bulk selection for assigned aliases with enable, disable, SOGo visibility and clipboard actions
- alias replacement workflow that creates a fresh address with the same purpose and SOGo visibility while keeping the previous alias disabled for traceability
- replacement format selection for name-based, readable-random or custom replacement addresses

### Changed

- `latest` is reserved for stable releases while `edge` follows `main`
- the updater selects `latest` or `edge` through `MOOLIAS_TAG` without requiring Compose edits between stable and beta updates
- name-based aliases now use a two-character ASCII letter/digit suffix with ambiguous characters excluded
- readable-random aliases now use exactly two short words of at most six characters plus a two-digit number
- both readable word lists contain 200–250 unique short words
- bulk selection now uses one tri-state select-all checkbox and a compact action dropdown below the alias list instead of separate selection and action buttons
- the alias replacement dialog has clearer spacing between the current address and replacement format selection
- the offline pool stays compact and scrolls internally instead of stretching the create-alias card
- alias edit popovers close when clicking outside them
- removed a redundant address-immutability hint from the alias creation form

## 0.1.0 - 2026-08-19

First public release.

### Highlights

- mailcow OAuth2 login without a separate Moolias user database
- mailbox-isolated alias management with server-side ownership checks
- name + random suffix, readable random and custom alias creation
- offline alias pool with individual assignment and deletion of unused entries
- active/disabled filtering, live search and pagination
- optional SOGo sender visibility per alias
- catch-all detection with a user-facing warning
- built-in German and English help dialog
- German and English UI with matching readable-word lists
- installable web app metadata for iPhone, iPad and macOS
- Docker Compose deployment and GHCR image publishing
- contributor, issue and pull-request templates plus CI

### Notes

- Alias data remains in mailcow; Moolias is stateless.
- Existing private mailcow admin comments are not exposed or modified.
- Main-mailbox sender blocking remains an administrator-side mail-server setting.
- Test the complete OAuth flow on installed Apple web apps before relying on that mode for daily use.
