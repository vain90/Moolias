from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class HousekeepingError(RuntimeError):
    pass


class HousekeepingSchemaError(HousekeepingError):
    pass


class HousekeepingDatabaseError(HousekeepingError):
    pass


@dataclass(frozen=True, slots=True)
class HousekeepingInventory:
    addresses: frozenset[str]
    alias_count: int
    mailbox_count: int


@dataclass(frozen=True, slots=True)
class HousekeepingEntry:
    address: str
    counts: tuple[tuple[str, int], ...]

    @property
    def total(self) -> int:
        return sum(count for _name, count in self.counts)


@dataclass(frozen=True, slots=True)
class HousekeepingReport:
    applied: bool
    candidates: tuple[HousekeepingEntry, ...]
    protected: tuple[HousekeepingEntry, ...]
    alias_count: int = 0
    mailbox_count: int = 0

    @property
    def candidate_rows(self) -> int:
        return sum(entry.total for entry in self.candidates)

    @property
    def protected_rows(self) -> int:
        return sum(entry.total for entry in self.protected)


@dataclass(frozen=True, slots=True)
class _AliasRule:
    table: str
    column: str
    report_name: str


_STATS_RULES = (
    _AliasRule("alias_usage", "alias", "stats.alias_usage"),
    _AliasRule("sender_usage", "alias", "stats.sender_usage"),
    _AliasRule("sender_expectations", "alias", "stats.sender_expectations"),
    _AliasRule("sender_alias_settings", "alias", "stats.sender_alias_settings"),
    _AliasRule("alias_usage_evidence", "alias", "stats.alias_usage_evidence"),
    _AliasRule("stats_history_alias_usage", "alias", "stats.stats_history_alias_usage"),
    _AliasRule("stats_history_sender_domain", "alias", "stats.stats_history_sender_domain"),
    _AliasRule("stats_history_sender_full", "alias", "stats.stats_history_sender_full"),
    _AliasRule("sender_spam_evidence", "alias", "stats.sender_spam_evidence"),
)
_NEWSLETTER_RULE = _AliasRule("newsletters", "recipient_alias", "newsletter.newsletters")
_WORKFLOW_TABLE = "alias_workflows"
_WORKFLOW_ADDRESS_COLUMNS = frozenset({"old_address", "new_address"})
_WORKFLOW_REQUIRED_COLUMNS = frozenset(
    {
        "old_address",
        "new_address",
        "completed_at",
        "bypass_expires_at",
        "bypass_cleared_at",
    }
)

# These names are deliberate alias-address references in the current schema. If a
# future table introduces one of these shapes without a rule above, housekeeping
# refuses to mutate anything until that lifecycle has been reviewed explicitly.
def _looks_like_alias_reference(column: str) -> bool:
    return (
        column == "alias"
        or column.endswith("_alias")
        or column in {"old_address", "new_address"}
        or column.endswith("alias_address")
    )


def _normalise_address(value: object) -> str:
    return str(value or "").strip().casefold()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _connect(path: Path, *, foreign_keys: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    if foreign_keys:
        connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _schema(connection: sqlite3.Connection) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    for row in rows:
        table = str(row["name"])
        columns = connection.execute(
            f"PRAGMA table_info({_quote_identifier(table)})"
        ).fetchall()
        result[table] = frozenset(str(column["name"]) for column in columns)
    return result


def _audit_schema(
    connection: sqlite3.Connection,
    *,
    rules: tuple[_AliasRule, ...],
    allow_workflows: bool,
    store_name: str,
) -> dict[str, frozenset[str]]:
    schema = _schema(connection)
    allowed: dict[str, set[str]] = defaultdict(set)
    for rule in rules:
        allowed[rule.table].add(rule.column)
    if allow_workflows:
        allowed[_WORKFLOW_TABLE].update(_WORKFLOW_ADDRESS_COLUMNS)

    for table, columns in schema.items():
        for column in columns:
            if _looks_like_alias_reference(column) and column not in allowed.get(table, set()):
                raise HousekeepingSchemaError(
                    f"{store_name} contains unreviewed alias reference "
                    f"{table}.{column}; refusing housekeeping"
                )

    for table, expected in allowed.items():
        if table not in schema:
            continue
        missing = expected - set(schema[table])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise HousekeepingSchemaError(
                f"{store_name} table {table} is missing expected column(s): {missing_text}"
            )

    if allow_workflows and _WORKFLOW_TABLE in schema:
        missing = _WORKFLOW_REQUIRED_COLUMNS - set(schema[_WORKFLOW_TABLE])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise HousekeepingSchemaError(
                f"{store_name} workflow schema is missing safety column(s): {missing_text}"
            )
    return schema


def _check_integrity(connection: sqlite3.Connection, store_name: str) -> None:
    rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
    if rows != ["ok"]:
        detail = "; ".join(rows[:5]) or "unknown error"
        raise HousekeepingDatabaseError(f"{store_name} integrity check failed: {detail}")


def _check_foreign_keys(connection: sqlite3.Connection, store_name: str) -> None:
    rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        raise HousekeepingDatabaseError(
            f"{store_name} foreign-key check failed with {len(rows)} violation(s)"
        )


def _audit_newsletter_relations(
    connection: sqlite3.Connection,
    schema: dict[str, frozenset[str]],
) -> None:
    known_children = {
        "newsletter_messages",
        "newsletter_unsubscribe_links",
    }
    for table in schema:
        relations = connection.execute(
            f"PRAGMA foreign_key_list({_quote_identifier(table)})"
        ).fetchall()
        newsletter_relations = [
            row for row in relations if str(row["table"]) == "newsletters"
        ]
        if not newsletter_relations:
            continue
        if table not in known_children:
            raise HousekeepingSchemaError(
                "newsletter database contains an unreviewed child table "
                f"{table} referencing newsletters; refusing housekeeping"
            )
        matching = [
            row
            for row in newsletter_relations
            if str(row["from"]) == "newsletter_id"
            and str(row["to"]) == "id"
            and str(row["on_delete"]).upper() == "CASCADE"
        ]
        if len(matching) != 1:
            raise HousekeepingSchemaError(
                f"newsletter database relation for {table} is not the expected "
                "newsletter_id -> newsletters.id ON DELETE CASCADE"
            )

    for table in known_children & set(schema):
        required = {"newsletter_id"}
        missing = required - set(schema[table])
        if missing:
            raise HousekeepingSchemaError(
                f"newsletter database table {table} is missing newsletter_id"
            )
        relations = connection.execute(
            f"PRAGMA foreign_key_list({_quote_identifier(table)})"
        ).fetchall()
        if not any(str(row["table"]) == "newsletters" for row in relations):
            raise HousekeepingSchemaError(
                f"newsletter database table {table} is missing its newsletters foreign key"
            )


def _rule_values(
    connection: sqlite3.Connection,
    rule: _AliasRule,
    schema: dict[str, frozenset[str]],
) -> dict[str, dict[str, int]]:
    if rule.table not in schema:
        return {}
    table = _quote_identifier(rule.table)
    column = _quote_identifier(rule.column)
    rows = connection.execute(
        f"""
        SELECT {column} AS value, COUNT(*) AS row_count
        FROM {table}
        WHERE {column} IS NOT NULL
          AND TRIM(CAST({column} AS TEXT)) <> ''
        GROUP BY {column}
        """
    ).fetchall()
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        raw = str(row["value"])
        normalized = _normalise_address(raw)
        if not normalized:
            continue
        result[normalized][raw] = int(row["row_count"])
    return dict(result)


def _protected_workflow_addresses(
    connection: sqlite3.Connection,
    schema: dict[str, frozenset[str]],
    *,
    now: int,
) -> frozenset[str]:
    if _WORKFLOW_TABLE not in schema:
        return frozenset()
    rows = connection.execute(
        """
        SELECT old_address, new_address
        FROM alias_workflows
        WHERE completed_at IS NULL
           OR (bypass_cleared_at IS NULL AND bypass_expires_at > ?)
        """,
        (int(now),),
    ).fetchall()
    result: set[str] = set()
    for row in rows:
        for column in ("old_address", "new_address"):
            value = _normalise_address(row[column])
            if value:
                result.add(value)
    return frozenset(result)


def _add_count(
    target: dict[str, dict[str, int]],
    address: str,
    report_name: str,
    count: int,
) -> None:
    if count:
        target.setdefault(address, {})[report_name] = (
            target.setdefault(address, {}).get(report_name, 0) + int(count)
        )


def _scan_rules(
    connection: sqlite3.Connection,
    schema: dict[str, frozenset[str]],
    rules: tuple[_AliasRule, ...],
) -> tuple[dict[str, dict[str, int]], dict[tuple[str, str], dict[str, dict[str, int]]]]:
    counts: dict[str, dict[str, int]] = {}
    raw_values: dict[tuple[str, str], dict[str, dict[str, int]]] = {}
    for rule in rules:
        values = _rule_values(connection, rule, schema)
        raw_values[(rule.table, rule.column)] = values
        for address, raw_counts in values.items():
            _add_count(counts, address, rule.report_name, sum(raw_counts.values()))
    return counts, raw_values


def _newsletter_child_counts(
    connection: sqlite3.Connection,
    schema: dict[str, frozenset[str]],
) -> dict[str, dict[str, int]]:
    if "newsletters" not in schema:
        return {}
    result: dict[str, dict[str, int]] = {}
    for child, report_name in (
        ("newsletter_messages", "newsletter.newsletter_messages"),
        ("newsletter_unsubscribe_links", "newsletter.newsletter_unsubscribe_links"),
    ):
        if child not in schema:
            continue
        rows = connection.execute(
            f"""
            SELECT n.recipient_alias AS address, COUNT(*) AS row_count
            FROM {_quote_identifier(child)} AS child
            JOIN newsletters AS n ON n.id = child.newsletter_id
            GROUP BY n.recipient_alias
            """
        ).fetchall()
        for row in rows:
            address = _normalise_address(row["address"])
            if address:
                _add_count(result, address, report_name, int(row["row_count"]))
    return result


def _merge_counts(*parts: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for part in parts:
        for address, table_counts in part.items():
            for name, count in table_counts.items():
                _add_count(result, address, name, count)
    return result


def _entries(
    counts: dict[str, dict[str, int]],
    addresses: Iterable[str],
) -> tuple[HousekeepingEntry, ...]:
    return tuple(
        HousekeepingEntry(
            address=address,
            counts=tuple(sorted(counts.get(address, {}).items())),
        )
        for address in sorted(set(addresses))
        if counts.get(address)
    )


def _classify(
    counts: dict[str, dict[str, int]],
    *,
    valid_addresses: frozenset[str],
    protected_addresses: frozenset[str],
) -> tuple[tuple[HousekeepingEntry, ...], tuple[HousekeepingEntry, ...]]:
    stored = set(counts)
    orphaned = stored - set(valid_addresses)
    protected = orphaned & set(protected_addresses)
    candidates = orphaned - protected
    return _entries(counts, candidates), _entries(counts, protected)


def _delete_raw_values(
    connection: sqlite3.Connection,
    rule: _AliasRule,
    raw_values: dict[str, dict[str, int]],
    candidates: set[str],
) -> int:
    if not candidates:
        return 0
    table = _quote_identifier(rule.table)
    column = _quote_identifier(rule.column)
    removed = 0
    for address in sorted(candidates):
        for raw in raw_values.get(address, {}):
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE {column} = ?",
                (raw,),
            )
            removed += int(cursor.rowcount)
    return removed


def _stats_operation(
    path: Path,
    *,
    valid_addresses: frozenset[str],
    apply: bool,
    now: int,
) -> tuple[
    tuple[HousekeepingEntry, ...],
    tuple[HousekeepingEntry, ...],
    frozenset[str],
]:
    if not path.is_file():
        raise HousekeepingDatabaseError(f"statistics/application database does not exist: {path}")
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        _check_integrity(connection, "statistics/application database")
        schema = _audit_schema(
            connection,
            rules=_STATS_RULES,
            allow_workflows=True,
            store_name="statistics/application database",
        )
        protected_addresses = _protected_workflow_addresses(connection, schema, now=now)
        counts, raw_values = _scan_rules(connection, schema, _STATS_RULES)
        candidates, protected = _classify(
            counts,
            valid_addresses=valid_addresses,
            protected_addresses=protected_addresses,
        )

        if apply:
            candidate_addresses = {entry.address for entry in candidates}
            removed_by_name: dict[str, int] = {}
            for rule in _STATS_RULES:
                values = raw_values.get((rule.table, rule.column), {})
                removed = _delete_raw_values(
                    connection,
                    rule,
                    values,
                    candidate_addresses,
                )
                if removed:
                    removed_by_name[rule.report_name] = removed
            expected_by_name: dict[str, int] = defaultdict(int)
            for entry in candidates:
                for name, count in entry.counts:
                    expected_by_name[name] += count
            if dict(expected_by_name) != removed_by_name:
                raise HousekeepingDatabaseError(
                    "statistics/application database changed during housekeeping; "
                    "refusing to commit a partial cleanup"
                )
            _check_integrity(connection, "statistics/application database")
            connection.commit()
        else:
            connection.rollback()
        return candidates, protected, protected_addresses
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def _newsletter_operation(
    path: Path,
    *,
    valid_addresses: frozenset[str],
    protected_addresses: frozenset[str],
    apply: bool,
) -> tuple[tuple[HousekeepingEntry, ...], tuple[HousekeepingEntry, ...]]:
    if not path.is_file():
        return (), ()
    connection = _connect(path, foreign_keys=True)
    try:
        connection.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        _check_integrity(connection, "newsletter database")
        _check_foreign_keys(connection, "newsletter database")
        schema = _audit_schema(
            connection,
            rules=(_NEWSLETTER_RULE,),
            allow_workflows=False,
            store_name="newsletter database",
        )
        _audit_newsletter_relations(connection, schema)
        direct_counts, raw_values = _scan_rules(connection, schema, (_NEWSLETTER_RULE,))
        child_counts = _newsletter_child_counts(connection, schema)
        counts = _merge_counts(direct_counts, child_counts)
        candidates, protected = _classify(
            counts,
            valid_addresses=valid_addresses,
            protected_addresses=protected_addresses,
        )

        if apply:
            candidate_addresses = {entry.address for entry in candidates}
            values = raw_values.get((_NEWSLETTER_RULE.table, _NEWSLETTER_RULE.column), {})
            expected_parents = sum(
                dict(entry.counts).get(_NEWSLETTER_RULE.report_name, 0)
                for entry in candidates
            )
            removed_parents = _delete_raw_values(
                connection,
                _NEWSLETTER_RULE,
                values,
                candidate_addresses,
            )
            if removed_parents != expected_parents:
                raise HousekeepingDatabaseError(
                    "newsletter database changed during housekeeping; "
                    "refusing to commit a partial cleanup"
                )
            _check_foreign_keys(connection, "newsletter database")
            _check_integrity(connection, "newsletter database")
            connection.commit()
        else:
            connection.rollback()
        return candidates, protected
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def _merge_entries(*groups: tuple[HousekeepingEntry, ...]) -> tuple[HousekeepingEntry, ...]:
    counts: dict[str, dict[str, int]] = {}
    for group in groups:
        for entry in group:
            for name, count in entry.counts:
                _add_count(counts, entry.address, name, count)
    return _entries(counts, counts)


def run_housekeeping(
    *,
    stats_db: str | Path,
    newsletter_db: str | Path,
    valid_addresses: Iterable[str],
    apply: bool = False,
    now: int | None = None,
    alias_count: int = 0,
    mailbox_count: int = 0,
) -> HousekeepingReport:
    timestamp = int(time.time()) if now is None else int(now)
    valid = frozenset(
        address
        for value in valid_addresses
        if (address := _normalise_address(value))
    )
    stats_candidates, stats_protected, protected_addresses = _stats_operation(
        Path(stats_db),
        valid_addresses=valid,
        apply=apply,
        now=timestamp,
    )

    # Re-read workflow protection after the stats transaction before touching the
    # separate newsletter store. New workflow state can only add protection here.
    if apply:
        connection = _connect(Path(stats_db))
        try:
            connection.execute("BEGIN")
            schema = _audit_schema(
                connection,
                rules=_STATS_RULES,
                allow_workflows=True,
                store_name="statistics/application database",
            )
            protected_addresses = protected_addresses | _protected_workflow_addresses(
                connection,
                schema,
                now=timestamp,
            )
            connection.rollback()
        finally:
            connection.close()

    newsletter_candidates, newsletter_protected = _newsletter_operation(
        Path(newsletter_db),
        valid_addresses=valid,
        protected_addresses=protected_addresses,
        apply=apply,
    )
    return HousekeepingReport(
        applied=apply,
        candidates=_merge_entries(stats_candidates, newsletter_candidates),
        protected=_merge_entries(stats_protected, newsletter_protected),
        alias_count=int(alias_count),
        mailbox_count=int(mailbox_count),
    )


async def load_mailcow_inventory(client: object) -> HousekeepingInventory:
    aliases, mailboxes = await asyncio.gather(
        client.list_aliases(),  # type: ignore[attr-defined]
        client.list_mailboxes(),  # type: ignore[attr-defined]
    )
    addresses: set[str] = set()
    for alias in aliases:
        address = _normalise_address(getattr(alias, "address", ""))
        if address:
            addresses.add(address)
    for mailbox in mailboxes:
        if not isinstance(mailbox, dict):
            continue
        address = _normalise_address(mailbox.get("username"))
        if address:
            addresses.add(address)
    return HousekeepingInventory(
        addresses=frozenset(addresses),
        alias_count=len(aliases),
        mailbox_count=len(mailboxes),
    )


def _print_entries(title: str, entries: tuple[HousekeepingEntry, ...]) -> None:
    if not entries:
        return
    print(title)
    for entry in entries:
        print(f"  {entry.address}")
        for name, count in entry.counts:
            print(f"    {name}: {count}")


def print_report(report: HousekeepingReport) -> None:
    mode = "APPLY" if report.applied else "DRY RUN"
    print(f"Moolias housekeeping - {mode}")
    print(
        "Mailcow inventory: "
        f"{report.alias_count} alias(es), {report.mailbox_count} mailbox(es)"
    )
    print()
    _print_entries("Protected by active/pending workflow:", report.protected)
    if report.protected:
        print()
    _print_entries("Orphaned Moolias alias data:", report.candidates)
    if not report.candidates:
        print("No orphaned Moolias alias data found.")
    else:
        print()
        if report.applied:
            print(
                f"Removed {report.candidate_rows} Moolias database row(s) "
                f"for {len(report.candidates)} orphaned address(es)."
            )
        else:
            print(
                f"Would remove {report.candidate_rows} Moolias database row(s) "
                f"for {len(report.candidates)} orphaned address(es)."
            )
            print("No changes made. Re-run with --apply to perform this cleanup.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find Moolias per-alias database state for addresses that no longer "
            "exist in Mailcow. Dry-run is the default."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete orphaned Moolias database rows after all safety checks pass",
    )
    parser.add_argument(
        "--stats-db",
        help="override MOOLIAS_USAGE_DB_PATH",
    )
    parser.add_argument(
        "--newsletter-db",
        help="override MOOLIAS_NEWSLETTER_DB_PATH",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    from moolias.config import get_settings
    from moolias.mailcow import MailcowClient, MailcowError

    settings = get_settings()
    client = MailcowClient(settings)
    try:
        try:
            inventory = await load_mailcow_inventory(client)
        except MailcowError as exc:
            raise HousekeepingError(f"could not load Mailcow inventory: {exc}") from exc
    finally:
        await client.close()

    report = run_housekeeping(
        stats_db=args.stats_db or settings.usage_db_path,
        newsletter_db=args.newsletter_db or settings.newsletter_db_path,
        valid_addresses=inventory.addresses,
        apply=bool(args.apply),
        alias_count=inventory.alias_count,
        mailbox_count=inventory.mailbox_count,
    )
    print_report(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_main_async(args))
    except (HousekeepingError, sqlite3.DatabaseError, OSError) as exc:
        print(f"Moolias housekeeping: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
