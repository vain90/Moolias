# Changelog

All notable changes to Moolias are documented here.

## 1.3.9 - 2026-09-03

### Changed

- aliases that Mailcow explicitly marks as unavailable for sending can no longer be enabled as SOGo senders through individual or bulk Moolias workflows; unknown sender availability remains non-blocking and Moolias never changes Mailcow's sender permission itself.
- sender/SOGo consistency is reconciled automatically every 15 minutes for aliases targeting Moolias-enabled mailboxes: if sending is later revoked, Moolias withdraws only SOGo visibility and does not automatically re-enable it if sending is allowed again.

### Fixed

- existing or externally created aliases no longer remain selectable in SOGo after their sender permission is explicitly revoked, while shared, catch-all, primary-mailbox and non-Moolias mailbox aliases remain outside the automatic reconciliation scope.

## 1.3.8 - 2026-09-03

### Added

- a dedicated `/readyz` readiness endpoint now verifies that the Mailcow API and required Mailcow Agent are actually usable, while `/healthz` remains the lightweight liveness probe.

### Changed

- stable updates now resolve the latest stable GitHub release first, pull the exact SemVer container tag instead of mutable `latest`, and verify the running image version after readiness succeeds; the intentionally mutable `edge` beta channel remains unchanged.
- Newsletter Management search now follows the Alias Management live-search interaction model: input is debounced, stale requests are aborted, filtering and pagination remain server-side, only the results area is refreshed, and the URL updates without a full-page reload.

### Fixed

- updater acceptance and rollback are now gated on application readiness, with compatibility for pre-readiness releases such as 1.3.7: an explicit missing `/readyz` endpoint on the previous image falls back to Docker health/liveness only for rollback, while newly started images still require strict readiness validation.

## 1.3.7 - 2026-09-02

### Changed

- Newsletter Management statistics now use two large summary cards below the primary alias-statistics row instead of five additional small metric cards, with a clearer overview of detected, unsubscribable and no-link newsletters.
- the new unsubscribe-success summary shows successful versus resumed-after-unsubscribe outcomes and calculates its rate only from newsletters with an actual unsubscribe outcome; when no outcome exists yet, the UI shows a neutral state instead of a misleading `0%`.

### Fixed

- native Moolias dialogs no longer interpret clicks on visible dialog padding or whitespace as backdrop clicks; intentional backdrop dismissal, explicit close controls and Escape behavior remain intact.
- dialog regression coverage now exercises real native-dialog surface targeting, repeated open/close cycles, form-state preservation and mobile behavior across representative dialog consumers.

## 1.3.6 - 2026-09-01

### Fixed

- expired authenticated browser sessions now return normal HTML navigation to the Moolias login/start page instead of exposing raw `{"detail":"Authentication required"}` responses across Overview, Alias Management, Offline Pool, Newsletter Management and Statistics.
- stale HTML form submissions after a session expires now return to login instead of exposing CSRF JSON, while API clients retain machine-readable `401` responses and genuine CSRF failures with a valid session remain `403`.
- regression coverage now exercises expired-session behavior centrally and through a real browser navigation flow so newly added rendered UI pages inherit the same safe behavior without a maintained route allowlist.

## 1.3.5 - 2026-08-30

### Added

- the Statistics page now shows conditional Newsletter Management totals for all senders, Unsubscribable, No link, Unsubscribed and After unsubscribe when the feature is effectively enabled for the mailbox.
- each metric links to the matching Newsletter filter and reuses the persisted server-side status classification without starting or waking the collector during Statistics rendering.

## 1.3.4 - 2026-08-30

### Changed

- authenticated navigation now shows immediate structural loading feedback while retaining native browser navigation and server-rendered Jinja/HTML as the source of truth, including mobile and reduced-motion handling.
- Newsletter Management now renders from persisted state without waiting for a request-bound Rspamd/Dovecot scan; the background collector is woken on first use instead.
- the Newsletter page uses a dedicated lightweight server-side state loader and shared UI loading reuses already-fetched Mailcow mailbox/domain data and runs independent alias/domain requests concurrently, avoiding unnecessary usage, sender, icon, health and overview calculations.

### Fixed

- alias workflow dialogs now clear their `workflow` URL parameter immediately when explicitly closed, preserving the existing no-reload behavior while keeping navigation loading feedback from interfering with workflow controls.

## 1.3.3 - 2026-08-30

### Fixed

- Newsletter Management now uses explicit server-rendered status filters for all, unsubscribable, no-link, after-unsubscribe and unsubscribed entries instead of the ambiguous `Active` state; legacy `status=active` URLs normalize to the unsubscribable view.
- automatic sender recognition now supports short 2–3 character alias identities such as VBL, DHL, O2, DM and ING when they exactly match the registered sender-domain label, without trusting one-character identities, short private-description hints or embedded/lookalike domains.

## 1.3.2 - 2026-08-29

### Added

- explicit orphaned-alias housekeeping via `python -m moolias.housekeeping`, with dry-run as the default and database mutation requiring `--apply`
- Mailcow-backed address inventory, active-workflow and live-bypass protection, fail-closed SQLite schema checks, newsletter cascade cleanup and per-table cleanup reporting
- dedicated housekeeping documentation plus unit and disposable real-Mailcow coverage for dry-run, apply, idempotence, current-schema compatibility and safety preflight behavior

### Security

- housekeeping never deletes Mailcow aliases, mailboxes or mail data, and preflights both Moolias SQLite stores before either database is changed
- completed replacement history and mailbox-wide policy/history state are retained intentionally while only reviewed per-alias orphaned state is eligible for cleanup

## 1.3.1 - 2026-08-29

### Changed

- the recommended same-host installer can optionally enable Newsletter Management in the same fresh interactive run; the separate stable-aware Newsletter installer remains available for enabling it later
- the Mailcow Agent installer refreshes registry-qualified images before starting the Agent, preventing a cached mutable tag such as `latest` from silently running stale code while local development images remain untouched

### Fixed

- installer-created Mailcow hook backups are made non-executable immediately, and installer reruns repair executable `*.before-moolias-agent-*.bak` leftovers before the Agent installer reaches Postfix or Rspamd restart paths
- explicit pinned-release and local-source installer paths continue to use their matching installer components instead of accidentally resolving through a different stable source

## 1.3.0 - 2026-08-28

### Added

- guided alias creation and replacement workflows with persistent server-side state that wait for the first accepted delivery before completing a migration
- an exact-recipient first-mail delivery bypass through the unified Mailcow Agent, with restart-safe state, automatic expiry and early cleanup after the expected delivery is detected
- independent old/new delivery tracking for replacement workflows plus explicit old-alias deactivation choices for now, later, 1 day, 7 days or 30 days
- server-side scheduled deactivation that continues without an open browser, together with Action required integration for pending alias changes

### Changed

- the first accepted sender for a waiting workflow is learned as expected at the configured sender-detail level without overriding an explicit manual unexpected decision
- replacement pairs remain linked and grouped while the migration is active, and the old alias stays active until the selected deactivation policy completes
- workflow, replacement, deactivation and Action required UI is rendered server-side; normal links and forms remain usable without JavaScript while JavaScript is limited to progressive enhancement and interaction
- long-running first-mail monitoring advances a per-workflow history cursor instead of repeatedly reopening the full historical Rspamd window
- the former sender-only sidecar is replaced by the unified required `moolias-agent`; same-host Moolias installations connect directly to `http://moolias-agent:8081`
- same-host Newsletter Management connects directly to `http://moolias-newsletter-agent:8082`, while authenticated Mailcow-nginx endpoints remain available for standalone deployments
- Newsletter Agent message retrieval now selects the message through Doveadm JSON first and fetches `text.utf8` separately using the selected mailbox GUID and UID
- service-logo assets are generated during the Docker image build and icon-picker enhancement is idempotent after server-rendered alias rows are refreshed

### Fixed

- opening an alias migration from Action required now uses the same server-rendered workflow view and styling as opening it from Alias Management
- confirming unexpected senders in Action required updates the sender row immediately and refreshes the underlying alias table when the dialog closes after changes
- partial multi-alias Offline Pool assignment failures reload the current server state instead of leaving already-applied changes represented by stale UI
- non-interactive installer runs no longer fail when `/dev/tty` cannot be opened
- direct same-host Mailcow Agent and Newsletter Agent routing avoids the internal nginx 502 path while keeping standalone fallback URLs intact
- first-mail sender learning continues correctly when the temporary delivery-bypass window has expired but the workflow is still waiting for its first accepted message

### Upgrade notes

- existing same-host installations using the older `moolias-sender-agent` layout must run the guided installer once before normal updater use; the migration preserves the existing Agent secret and managed sender-protection state
- existing administrator-managed sender-login rules remain separate unless explicitly imported; unattended migration keeps recognized manual rules external by default

### Security

- the first-mail bypass is restricted to exact recipients and suppresses only greylisting behavior; normal spam, antivirus and other Rspamd checks remain active
- the unified Mailcow Agent remains hardened without a Docker socket, Mailcow API key or database credentials and writes only its dedicated state, Postfix policy and Rspamd map paths

## 1.2.1 - 2026-08-26

### Added

- a dedicated success dialog after alias creation with the new alias address, clipboard action and compact alias metadata
- a non-dismissible, full-width warning when JavaScript is disabled, rendered server-side and styled without JavaScript

### Changed

- alias address, private description, replacement controls and activate/deactivate labels are rendered in the initial server response instead of being rebuilt asynchronously in the browser
- Offline-Pool assignment descriptions are rendered server-side so the no-JavaScript and interactive views use the same final content

### Fixed

- the JavaScript-disabled warning remains a single stable banner with its text physically inside the yellow background, including Firefox setups where a NoScript-style extension rewrites `<noscript>` markup
- JavaScript-disabled browser coverage now verifies the warning geometry and server-rendered alias UI directly in Firefox as well as Chromium

## 1.2.0 - 2026-08-25

### Added

- optional Newsletter Management with an inheritable Mailcow domain/mailbox tag policy and a dedicated German/English management view
- newsletter discovery from Mailcow Rspamd history using standard mailing-list signals plus the zero-score `MOOLIAS_BODY_UNSUB` detector for providers that expose unsubscribe actions only in the message body
- a restricted HMAC-authenticated Newsletter Agent that resolves only an exact mailbox and Message-ID through Dovecot and returns fixed newsletter metadata instead of exposing mail storage to the Moolias web application
- verified RFC 8058 one-click unsubscribe handling, ordinary HTTPS unsubscribe-page support, manual unsubscribe status tracking and warnings when a sender writes again after an unsubscribe
- optional inclusion of active direct Mailcow forwarding aliases and administratively linked legacy Mailcow mailboxes using `moolias-newsletter-link-<id>-target` / `moolias-newsletter-link-<id>-source` tags
- a stable-aware `install-newsletter.sh` bootstrap that retrieves the Newsletter Agent installer, Rspamd installer and Lua detector from the same Moolias release
- unit, browser and disposable real-Mailcow coverage for newsletter policy, persistence, agent behavior, Rspamd configuration and body-only unsubscribe extraction

### Changed

- enabling Newsletter Management from an effective Off state asks whether still-available history should be included or detection should begin only from that point forward
- the Newsletter Agent now follows the configured Moolias image and stable tag by default instead of using the unreleased `edge` channel
- the Newsletter installer recreates the Moolias application after enabling the feature when the standard Mailcow-host Compose installation is present
- linked legacy mailboxes are resolved from explicit Mailcow tags at most once per authenticated session and cached in the application process; the collector does not parse Sieve filters or fetch the full mailbox list on every polling cycle
- stable release publication now waits for both the normal CI workflow and the disposable real-Mailcow integration workflow to pass for the same `main` commit
- Newsletter pagination and navigation styling now follow the existing Alias Management UI, including the Lucide `newspaper` navigation icon

### Security

- the Moolias web container never receives the Dovecot `doveadm_password`, Mailcow mail volume or Docker socket for Newsletter Management
- the Newsletter Agent runs as uid 10001 with a read-only root filesystem, no host mounts, no published ports, no new privileges and all Linux capabilities dropped
- message text may be inspected inside the restricted agent only for an exact Message-ID that Rspamd marked with `MOOLIAS_BODY_UNSUB`; the body itself is never returned to or stored by the Moolias application
- server-side one-click requests accept only HTTPS on port 443, reject credentials and non-public destinations, retain hostname verification for TLS and do not follow redirects
- the Rspamd body detector has score `0.0` and records no personalized unsubscribe URL in Rspamd history

## 1.1.8 - 2026-08-24

### Added

- optional per-alias private descriptions backed by Mailcow's `private_comment`, while the public comment remains the alias name
- description editing when creating or editing aliases and when assigning Offline-Pool aliases
- a dedicated description column in the alias table with ellipsis previews, full-text info popovers and a compact mobile-only info control
- private-description hints for conservative sender recognition without giving description text the same trust weight as the alias name

### Changed

- only `[moolias:...]` entries in Mailcow private comments are treated as internal Moolias metadata; all other private-comment text is exposed as the user-facing description
- Moolias marker updates preserve human description text and unrelated Moolias markers instead of replacing the complete private comment
- alias replacement carries both the public alias name and private description to the replacement alias
- alias editing now labels the public comment simply as `Alias Name`, shows the alias address explicitly and presents the description as a full-width multiline field
- the alias table separates `Alias Name / Alias-Adresse` from `Beschreibung`; empty descriptions show a dash and mobile layouts hide the preview text while retaining access to the full description

### Removed

- legacy reservation-marker recognition; only Moolias markers are interpreted as internal metadata

## 1.1.7 - 2026-08-24

### Added

- a concise 13-step guided onboarding tour for non-technical users, with a plain-language help dialog that can restart the tour at any time
- browser E2E coverage that walks every onboarding step on desktop and mobile and verifies that both the highlighted target and tour popover stay inside the visible viewport

### Changed

- statistics guidance now clearly distinguishes server-disabled, mailbox-disabled and temporarily unavailable states and links administrators to the activation documentation where appropriate
- onboarding copy now adapts to whether usage statistics and primary-address protection are actually enabled by the administrator instead of presenting optional server features as universally available
- action-required and settings guidance now describes primary-address protection and sender-review features conditionally, according to the features enabled on the server
- tour scrolling now only moves the page when necessary, keeps header controls in place and reserves room for the mobile tour popover instead of centering every target unconditionally

### Fixed

- the alias-creation steps no longer scroll the `New alias` button away from the top of the page when it is already visible
- the tour popover now has a safe initial viewport position before dynamic placement, avoiding a transient off-screen jump between steps on long pages
- the narrow statistics review action remains readable on small layouts

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

- the public Mailcow bootstrap now recognizes an already enabled sender-protection setup during a repair/rerun and preserves it without asking the child installer to install it again
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

- the public Mailcow bootstrap now detects the actual Mailcow Docker-network IPv4 CIDR and tells the administrator exactly what to allow for the Moolias read/write API key before asking for the key
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
