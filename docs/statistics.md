# Usage statistics

Moolias usage statistics are optional and globally disabled by default. Enabling the server-side feature and choosing a statistics mode for a mailbox are two separate steps.

## 1. Enable statistics on the Moolias server

For the recommended same-host Mailcow installation, edit `/opt/moolias/.env` and set:

```dotenv
MOOLIAS_USAGE_STATS=true
```

Then recreate the Moolias container so the changed environment is loaded:

```bash
cd /opt/moolias
docker compose up -d --force-recreate moolias
```

You can verify the running container received the setting with:

```bash
cd /opt/moolias
docker compose exec -T moolias env | grep '^MOOLIAS_USAGE_STATS='
```

The expected result is:

```text
MOOLIAS_USAGE_STATS=true
```

For standalone deployments, set the same variable in the environment used by your Moolias container and recreate or redeploy that container.

## 2. Choose a statistics mode

After the server-side feature is enabled, each mailbox can use its domain default or select its own mode in **Moolias → Settings → Usage statistics**.

Available modes are:

| Mode | Stored information |
| --- | --- |
| `off` | No new usage statistics |
| `basic` | Received and sent counters |
| `domain` | Counters plus sender-domain aggregates |
| `full` | Counters plus full sender-address aggregates |

A mailbox with no enabled mode does not collect usage statistics even when `MOOLIAS_USAGE_STATS=true` on the server.

Increasing the detail level can evaluate still-available Mailcow/Rspamd history. Reducing the detail level removes or collapses stored details that the new privacy mode no longer permits.

Statistics and review state are stored in the persistent SQLite database configured by `MOOLIAS_USAGE_DB_PATH`. Alias configuration itself remains in Mailcow.

For collector diagnostics and Rspamd-history coverage, see [Statistics collector health](statistics-collector-health.md).
