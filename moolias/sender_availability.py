from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

from fastapi import APIRouter

from moolias.aliases import AliasRecord, is_owned_alias, is_primary_mailbox_alias
from moolias.mailcow import MailcowAccessDenied, MailcowClient, MailcowError

LOGGER = logging.getLogger(__name__)
SENDER_VISIBILITY_HOUSEKEEPING_SECONDS = 900


@dataclass(frozen=True, slots=True)
class SenderVisibilityMismatch:
    alias_id: int
    address: str
    mailbox: str


def sender_available(alias: AliasRecord) -> bool:
    """Treat only an explicit Mailcow denial as unavailable."""
    return alias.sender_allowed is not False


def sender_visibility_inconsistent(alias: AliasRecord) -> bool:
    return alias.sender_allowed is False and alias.sogo_visible


def _managed_mailbox(alias: AliasRecord) -> str | None:
    mailbox = alias.goto.strip().lower()
    if not mailbox:
        return None
    try:
        if not is_owned_alias(alias, mailbox):
            return None
        if is_primary_mailbox_alias(alias, mailbox):
            return None
    except ValueError:
        return None
    return mailbox


async def find_sender_visibility_mismatches(
    client: MailcowClient,
) -> tuple[SenderVisibilityMismatch, ...]:
    aliases = await client.list_aliases()
    mailbox_access: dict[str, bool] = {}
    mismatches: list[SenderVisibilityMismatch] = []

    for alias in aliases:
        if not sender_visibility_inconsistent(alias):
            continue
        mailbox = _managed_mailbox(alias)
        if mailbox is None:
            continue

        if mailbox not in mailbox_access:
            try:
                await client.get_mailbox(mailbox)
            except (MailcowAccessDenied, MailcowError):
                mailbox_access[mailbox] = False
            else:
                mailbox_access[mailbox] = True
        if not mailbox_access[mailbox]:
            continue

        mismatches.append(
            SenderVisibilityMismatch(
                alias_id=alias.id,
                address=alias.address,
                mailbox=mailbox,
            )
        )

    return tuple(mismatches)


async def reconcile_sender_visibility(client: MailcowClient) -> tuple[SenderVisibilityMismatch, ...]:
    mismatches = await find_sender_visibility_mismatches(client)
    if mismatches:
        await client.set_sogo_visible_many(
            [mismatch.alias_id for mismatch in mismatches],
            False,
        )
    return mismatches


async def _run_housekeeping(app) -> None:
    while True:
        try:
            mismatches = await reconcile_sender_visibility(app.state.mailcow)
            if mismatches:
                LOGGER.info(
                    "Removed SOGo sender visibility from %d non-sendable alias(es)",
                    len(mismatches),
                )
        except Exception:
            # Consistency repair must never affect application availability.
            LOGGER.exception("Sender visibility housekeeping failed")
        await asyncio.sleep(SENDER_VISIBILITY_HOUSEKEEPING_SECONDS)


@asynccontextmanager
async def _lifespan(app):
    task = asyncio.create_task(
        _run_housekeeping(app),
        name="moolias-sender-visibility-housekeeping",
    )
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


router = APIRouter(lifespan=_lifespan)
