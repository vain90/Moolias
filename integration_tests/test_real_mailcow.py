from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from moolias.aliases import RESERVED_COMMENT
from moolias.config import Settings
from moolias.mailcow import MailcowClient
from moolias.newsletters import NewsletterAgentClient
from moolias.stats_mode import replace_mailbox_stats_tags

DOMAIN = "moolias-ci.test"
MAILBOX = f"owner@{DOMAIN}"
ACCESS_TAG = "moolias-ci-access"
STATS_TAG = "moolias-stats"
PASSWORD = "Moolias-CI-Only-4f9d!A7"
NEWSLETTER_AGENT_SECRET = "newsletter-ci-agent-secret-0123456789abcdef0123456789abcdef"
DOVEADM_PASSWORD = "newsletter-ci-doveadm-0123456789abcdef0123456789abcdef"
NEWSLETTER_MESSAGE_ID = "moolias-newsletter-agent-ci@example.net"
BODY_NEWSLETTER_MESSAGE_ID = "moolias-newsletter-body-ci@example.net"


@dataclass
class RealMailcow:
    client: MailcowClient


async def _post_success(
    admin: httpx.AsyncClient,
    path: str,
    payload: dict[str, object],
) -> object:
    response = await admin.post(path, json=payload)
    response.raise_for_status()
    body = response.json()
    entries = body if isinstance(body, list) else [body]
    result_types = [
        str(getattr(entry, "get", lambda *_: "")("type", "")).strip().casefold()
        for entry in entries
    ]
    if "success" not in result_types:
        raise AssertionError(
            f"Mailcow {path} did not report success "
            f"(result types: {result_types}): {body!r}"
        )
    return body


async def _create_domain(admin: httpx.AsyncClient) -> None:
    await _post_success(
        admin,
        "/api/v1/add/domain",
        {
            "active": 1,
            "aliases": 50,
            "backupmx": 0,
            "defquota": 128,
            "description": "Disposable Moolias integration domain",
            "domain": DOMAIN,
            "mailboxes": 10,
            "maxquota": 512,
            "quota": 1024,
            "relay_all_recipients": 0,
            "rl_frame": "s",
            "rl_value": 10,
            "restart_sogo": 0,
            "tags": [ACCESS_TAG],
        },
    )


async def _create_mailbox(admin: httpx.AsyncClient) -> None:
    await _post_success(
        admin,
        "/api/v1/add/mailbox",
        {
            "active": 1,
            "domain": DOMAIN,
            "local_part": "owner",
            "name": "Moolias CI",
            "password": PASSWORD,
            "password2": PASSWORD,
            "quota": 128,
            "force_pw_update": 0,
            "tls_enforce_in": 0,
            "tls_enforce_out": 0,
        },
    )


def _settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="http://moolias-ci.test",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_ACCESS_TAG=ACCESS_TAG,
        MAILCOW_URL=os.environ["MAILCOW_URL"],
        MAILCOW_API_KEY=os.environ["MAILCOW_API_KEY"],
        MAILCOW_OAUTH_CLIENT_ID="integration-not-used",
        MAILCOW_OAUTH_CLIENT_SECRET="integration-not-used",
        MAILCOW_VERIFY_TLS=False,
    )


@pytest.fixture(scope="module")
async def provision_real_mailcow() -> None:
    base_url = os.environ.get("MAILCOW_URL")
    api_key = os.environ.get("MAILCOW_API_KEY")
    if not base_url or not api_key:
        pytest.skip("real Mailcow integration environment is not configured")

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        timeout=30.0,
        trust_env=False,
    ) as admin:
        await _create_domain(admin)
        await _create_mailbox(admin)


@pytest.fixture
async def real_mailcow(provision_real_mailcow: None) -> AsyncIterator[RealMailcow]:
    client = MailcowClient(_settings())
    try:
        yield RealMailcow(client=client)
    finally:
        await client.close()


async def _alias_by_address(real_mailcow: RealMailcow, address: str):
    aliases = await real_mailcow.client.list_aliases()
    return next(alias for alias in aliases if alias.address == address)


async def test_profile_mailbox_identity_and_domain_access_tag(real_mailcow: RealMailcow):
    mailbox = await real_mailcow.client.get_mailbox(MAILBOX)

    assert mailbox["username"] == MAILBOX
    assert mailbox["domain"] == DOMAIN


async def test_alias_create_read_edit_disable_and_delete_contract(real_mailcow: RealMailcow):
    address = f"lifecycle@{DOMAIN}"

    await real_mailcow.client.create_alias(
        address,
        MAILBOX,
        "Initial purpose",
        private_comment="private-integration-marker",
        sogo_visible=True,
    )
    created = await _alias_by_address(real_mailcow, address)

    assert created.goto == MAILBOX
    assert created.public_comment == "Initial purpose"
    assert created.private_comment == "private-integration-marker"
    assert created.sogo_visible is True
    assert created.sender_allowed is True
    assert created.active is True

    await real_mailcow.client.update_alias_preferences(created.id, "Updated purpose", False)
    updated = await real_mailcow.client.get_alias(created.id)
    assert updated.public_comment == "Updated purpose"
    assert updated.private_comment == "private-integration-marker"
    assert updated.sogo_visible is False

    await real_mailcow.client.set_active(created.id, False)
    disabled = await real_mailcow.client.get_alias(created.id)
    assert disabled.active is False

    await real_mailcow.client.set_active(created.id, True)
    await real_mailcow.client.delete_alias(created.id)
    assert all(alias.address != address for alias in await real_mailcow.client.list_aliases())


async def test_reserved_and_reserved_used_markers_round_trip(real_mailcow: RealMailcow):
    address = f"reserved@{DOMAIN}"

    await real_mailcow.client.create_alias(
        address,
        MAILBOX,
        private_comment=RESERVED_COMMENT,
        sogo_visible=False,
    )
    reserved = await _alias_by_address(real_mailcow, address)
    assert reserved.is_reserved is True
    assert reserved.is_reserved_used is False
    assert reserved.sogo_visible is False

    await real_mailcow.client.mark_reserved_alias_used(reserved.id)
    used = await real_mailcow.client.get_alias(reserved.id)
    assert used.is_reserved is True
    assert used.is_reserved_used is True

    await real_mailcow.client.assign_reserved_alias(reserved.id, "Assigned purpose", True)
    assigned = await real_mailcow.client.get_alias(reserved.id)
    assert assigned.is_reserved is False
    assert assigned.is_reserved_used is False
    assert assigned.private_comment == ""
    assert assigned.public_comment == "Assigned purpose"
    assert assigned.sogo_visible is True

    await real_mailcow.client.delete_alias(reserved.id)


async def test_mailbox_tag_add_remove_and_stats_mode_replacement(real_mailcow: RealMailcow):
    await real_mailcow.client.set_mailbox_tags(
        MAILBOX,
        ["keep-me", f"{STATS_TAG}-domain"],
    )
    domain_mode = await real_mailcow.client.get_mailbox(MAILBOX)
    assert {tag.casefold() for tag in domain_mode.get("tags", [])} == {
        "keep-me",
        f"{STATS_TAG}-domain",
    }

    full_tags = replace_mailbox_stats_tags(domain_mode.get("tags"), STATS_TAG, "full")
    await real_mailcow.client.set_mailbox_tags(MAILBOX, full_tags)
    full_mode = await real_mailcow.client.get_mailbox(MAILBOX)
    assert {tag.casefold() for tag in full_mode.get("tags", [])} == {
        "keep-me",
        f"{STATS_TAG}-full",
    }

    await real_mailcow.client.set_mailbox_tags(MAILBOX, ["keep-me"])
    without_stats = await real_mailcow.client.get_mailbox(MAILBOX)
    assert {tag.casefold() for tag in without_stats.get("tags", [])} == {"keep-me"}


async def test_rspamd_history_endpoint_is_reachable(real_mailcow: RealMailcow):
    history = await real_mailcow.client.get_rspamd_history(10)
    assert isinstance(history, list)


def _docker_compose(
    mailcow_dir: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=mailcow_dir,
        input=input_bytes,
        check=True,
        capture_output=True,
        timeout=180,
    )


async def test_zz_newsletter_agent_reads_headers_through_remote_doveadm(
    real_mailcow: RealMailcow,
    tmp_path: Path,
):
    # The fixture guarantees that the target mailbox exists before Dovecot is exercised.
    assert (await real_mailcow.client.get_mailbox(MAILBOX))["username"] == MAILBOX

    repository_root = Path(__file__).resolve().parents[1]
    mailcow_dir = Path(os.environ["MAILCOW_DIR"])
    moolias_dir = tmp_path / "moolias"
    moolias_dir.mkdir()
    (moolias_dir / ".env").write_text(
        "MAILCOW_INTERNAL_URL=http://nginx-mailcow:80\n",
        encoding="utf-8",
    )

    agent_image = os.environ.get("MOOLIAS_AGENT_IMAGE", "moolias:newsletter-agent-ci")
    image_exists = subprocess.run(
        ["docker", "image", "inspect", agent_image],
        check=False,
        capture_output=True,
    ).returncode == 0
    if not image_exists:
        subprocess.run(
            ["docker", "build", "-t", agent_image, "."],
            cwd=repository_root,
            check=True,
            timeout=300,
        )

    installer_env = os.environ.copy()
    installer_env.update(
        {
            "MAILCOW_DIR": str(mailcow_dir),
            "MOOLIAS_DIR": str(moolias_dir),
            "MOOLIAS_AGENT_IMAGE": agent_image,
            "MOOLIAS_NEWSLETTER_AGENT_SECRET": NEWSLETTER_AGENT_SECRET,
            "MOOLIAS_DOVEADM_PASSWORD": DOVEADM_PASSWORD,
        }
    )
    preserved_env = ",".join(
        (
            "MAILCOW_DIR",
            "MOOLIAS_DIR",
            "MOOLIAS_AGENT_IMAGE",
            "MOOLIAS_NEWSLETTER_AGENT_SECRET",
            "MOOLIAS_DOVEADM_PASSWORD",
        )
    )
    subprocess.run(
        [
            "sudo",
            f"--preserve-env={preserved_env}",
            "bash",
            str(repository_root / "scripts" / "install-newsletter-agent.sh"),
        ],
        cwd=repository_root,
        env=installer_env,
        check=True,
        timeout=180,
    )

    rspamd_plugin = mailcow_dir / "data/conf/rspamd/plugins.d/moolias_newsletter.lua"
    assert rspamd_plugin.exists()
    assert "MOOLIAS_BODY_UNSUB" in rspamd_plugin.read_text(encoding="utf-8")
    rspamd_local = mailcow_dir / "data/conf/rspamd/rspamd.conf.local"
    assert "moolias_newsletter { }" in rspamd_local.read_text(encoding="utf-8")

    message = (
        "From: Moolias Newsletter CI <news@example.net>\r\n"
        f"To: {MAILBOX}\r\n"
        f"Message-ID: <{NEWSLETTER_MESSAGE_ID}>\r\n"
        "Subject: Newsletter agent integration\r\n"
        "List-ID: Moolias Newsletter CI <newsletter.example.net>\r\n"
        "List-Unsubscribe: <https://example.net/unsubscribe?token=ci>, "
        "<mailto:leave@example.net>\r\n"
        "List-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.net; s=ci; "
        "h=from:to:subject:list-unsubscribe:list-unsubscribe-post; bh=abc; b=def\r\n"
        "\r\n"
        "Disposable Mailcow integration message.\r\n"
    ).encode()
    _docker_compose(
        mailcow_dir,
        "exec",
        "-T",
        "dovecot-mailcow",
        "doveadm",
        "save",
        "-u",
        MAILBOX,
        "-m",
        "INBOX",
        "-",
        input_bytes=message,
    )

    body_message = (
        "From: Body Newsletter CI <body-news@example.net>\r\n"
        f"To: {MAILBOX}\r\n"
        f"Message-ID: <{BODY_NEWSLETTER_MESSAGE_ID}>\r\n"
        "Subject: Body-only newsletter integration\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Angebot und Produktinformationen.\r\n\r\n"
        "Abbestellen (https://example.net/body-unsubscribe?token=ci-body)\r\n"
    ).encode()
    _docker_compose(
        mailcow_dir,
        "exec",
        "-T",
        "dovecot-mailcow",
        "doveadm",
        "save",
        "-u",
        MAILBOX,
        "-m",
        "INBOX",
        "-",
        input_bytes=body_message,
    )

    async with NewsletterAgentClient(
        f"{os.environ['MAILCOW_URL']}/moolias-newsletter-agent",
        NEWSLETTER_AGENT_SECRET,
        verify_tls=False,
    ) as agent:
        headers = await agent.fetch_headers(MAILBOX, NEWSLETTER_MESSAGE_ID)
        body_headers = await agent.fetch_headers(
            MAILBOX,
            BODY_NEWSLETTER_MESSAGE_ID,
            include_body_unsubscribe=True,
        )

    assert headers["matches"] >= 1
    assert headers["from"] == "Moolias Newsletter CI <news@example.net>"
    assert headers["list_id"] == "Moolias Newsletter CI <newsletter.example.net>"
    assert headers["list_unsubscribe"] == (
        "<https://example.net/unsubscribe?token=ci>, <mailto:leave@example.net>"
    )
    assert headers["list_unsubscribe_post"] == "List-Unsubscribe=One-Click"

    assert body_headers["matches"] >= 1
    assert body_headers["list_unsubscribe"] == ""
    assert body_headers["body_unsubscribe_url"] == (
        "https://example.net/body-unsubscribe?token=ci-body"
    )
