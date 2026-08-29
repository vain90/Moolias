# Housekeeping orphaned alias data

Mailcow remains the source of truth for aliases and mailboxes. Moolias keeps additional local SQLite state for statistics, sender review, alias workflows and optional Newsletter Management.

When an alias is deleted in Mailcow, historical Moolias rows for that address can remain. The housekeeping command detects such orphaned per-alias state and can remove it without changing Mailcow itself.

## Dry-run first

For the recommended same-host installation under `/opt/moolias`:

```bash
cd /opt/moolias
docker compose exec -T moolias python -m moolias.housekeeping
```

Dry-run is the default. It reads the current Mailcow alias/mailbox inventory, checks the Moolias SQLite schemas and reports the orphaned addresses plus per-table row counts that would be removed.

No database rows are changed without `--apply`.

## Apply cleanup

After reviewing the dry-run output:

```bash
cd /opt/moolias
docker compose exec -T moolias python -m moolias.housekeeping --apply
```

`--apply` repeats the full read-only preflight before changing either database. Each Moolias database is then changed in its own SQLite write transaction and checked again before commit.

Take or verify your normal Moolias data backup before applying maintenance on production data.

## What counts as a valid address

Housekeeping builds the valid-address inventory from:

- every current Mailcow alias address;
- every current Mailcow mailbox username.

Mailbox usernames are included because Newsletter Management can legitimately record a newsletter delivered directly to a primary mailbox rather than an alias.

An address that still exists anywhere in that Mailcow inventory is not removed by housekeeping.

## Data covered

The current housekeeping rules cover per-alias rows in the shared Moolias application/statistics database, including:

- alias usage counters;
- sender usage and sender expectations;
- per-alias sender-review settings;
- alias usage evidence;
- historical alias/sender statistics;
- stored Rspamd spam evidence used by sender review.

If the Newsletter database exists, housekeeping also removes orphaned `newsletters` rows. The existing foreign-key cascades remove their dependent newsletter-message and unsubscribe-link rows in the same transaction.

A Newsletter database that has not been created yet is normal and is simply skipped.

## Workflow safety

Addresses are protected from cleanup while they are referenced by an active or pending alias workflow. A completed workflow is also protected while its first-mail delivery bypass is still live and has not been cleared.

Completed replacement workflow rows themselves are retained as intentional migration history. Housekeeping may remove obsolete statistics/newsletter rows for an old address after the replacement is complete, but it does not erase the replacement-history record.

## Intentionally not removed

Housekeeping does not remove mailbox-wide configuration or history state merely because one alias disappeared. This includes statistics policy/backfill state and other mailbox-level metadata.

Deduplication tables store one-way event hashes rather than recoverable alias addresses. They are therefore not guessed or reverse-mapped by housekeeping and continue to follow their existing retention/pruning behavior.

Housekeeping never deletes:

- Mailcow aliases or mailboxes;
- messages or Maildir data;
- Mailcow configuration;
- active/pending alias workflow state;
- completed replacement history.

## Schema safety

Before reporting or deleting data, housekeeping inspects the actual SQLite schema and runs integrity checks. Newsletter foreign-key relationships are validated as well.

If a future Moolias version introduces an alias-reference column or a Newsletter child table that has not been explicitly reviewed for housekeeping, the command fails instead of guessing how that new state should be deleted.

This behavior is intentional: a partial cleanup that silently leaves related state behind is less safe than refusing maintenance until the new lifecycle is defined.

## Database-path overrides

For development, recovery copies or targeted testing, the configured database paths can be overridden:

```bash
python -m moolias.housekeeping \
  --stats-db /path/to/moolias-stats.sqlite3 \
  --newsletter-db /path/to/moolias-newsletters.sqlite3
```

Add `--apply` only when the supplied database copies are intended to be modified.
