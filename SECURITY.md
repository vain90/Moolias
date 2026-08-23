# Security policy

Moolias holds a mailcow read/write API key and must therefore be treated as a privileged service.

Please do not open public issues for vulnerabilities that could expose mailboxes, aliases, OAuth credentials, API keys, or session data. Use GitHub's private vulnerability reporting when it is enabled for this repository.

## Deployment recommendations

- Serve Moolias only over HTTPS.
- Restrict the mailcow API key to the Moolias source address or Docker network where practical.
- Keep `MOOLIAS_COOKIE_SECURE=true` in production.
- Use a randomly generated session secret of at least 32 bytes.
- Do not expose `.env` files, API keys, or OAuth client secrets to the browser.
- Put Moolias and mailcow behind maintained reverse proxies and keep both updated.

## Recommended Mailcow-host deployment

The recommended same-host installation keeps Moolias as a separate Compose project. The main application joins Mailcow's existing Docker network so `nginx-mailcow` can proxy the dedicated Moolias hostname internally.

The Moolias application must not receive:

- the Docker socket;
- Mailcow database credentials;
- Mailcow configuration directories;
- Postfix configuration mounts;
- arbitrary host filesystem mounts.

Its only persistent application mount is `/data`, normally backed by the dedicated `moolias-data` Docker volume. The recommended Compose file publishes no application host port.

The optional primary-sender-protection agent is deliberately separate from the main application. It has its own narrower filesystem permissions and security model; see [docs/sender-protection.md](docs/sender-protection.md).

The guided Mailcow-host installer refuses to overwrite an unrelated Mailcow nginx `moolias.conf` or an unmanaged existing Moolias installation. Installer-managed files are backed up before replacement.
