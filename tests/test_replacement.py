import os
from contextlib import contextmanager

from fastapi.testclient import TestClient

from moolias.aliases import AliasRecord
from moolias.config import Settings
from moolias.mailcow import MailcowError

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

import moolias.alias_table_ui as alias_table_module  # noqa: E402
import moolias.main as main_module  # noqa: E402


def settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, alias: AliasRecord, *, fail_disable: bool = False) -> None:
        self.alias = alias
        self.fail_disable = fail_disable
        self.created: list[dict[str, object]] = []
        self.active_updates: list[tuple[int, bool]] = []

    async def close(self) -> None:
        pass

    async def get_mailbox(self, email: str):
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": [],
        }

    async def get_alias(self, alias_id: int) -> AliasRecord:
        assert alias_id == self.alias.id
        return self.alias

    async def create_alias(
        self,
        address: str,
        target: str,
        public_comment: str = "",
        *,
        private_comment: str = "",
        sogo_visible: bool = False,
    ) -> None:
        self.created.append(
            {
                "address": address,
                "target": target,
                "public_comment": public_comment,
                "private_comment": private_comment,
                "sogo_visible": sogo_visible,
            }
        )

    async def set_active(self, alias_id: int, active: bool) -> None:
        self.active_updates.append((alias_id, active))
        if self.fail_disable:
            raise MailcowError("disable failed")


def alias_record(**overrides) -> AliasRecord:
    values = {
        "id": 42,
        "address": "amazon-k7@example.org",
        "goto": "hidden@example.org",
        "domain": "example.org",
        "active": True,
        "private_comment": "",
        "public_comment": "Amazon",
        "sogo_visible": True,
    }
    values.update(overrides)
    return AliasRecord(**values)


@contextmanager
def make_client(monkeypatch, fake: FakeMailcow):
    async def fake_exchange_code(_settings, _code):
        return {"email": "hidden@example.org"}

    monkeypatch.setattr(main_module, "MailcowClient", lambda _: fake)
    monkeypatch.setattr(main_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(main_module, "validate_oauth_state", lambda _request, _state: None)
    monkeypatch.setattr(main_module, "validate_csrf", lambda _request, _token: None)
    monkeypatch.setattr(alias_table_module, "validate_csrf", lambda _request, _token: None)

    with TestClient(main_module.create_app(settings())) as client:
        login = client.get(
            "/oauth/callback?code=test&state=test",
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"] == "/overview"
        yield client


def test_replace_alias_copies_name_description_and_sogo_then_disables_old_alias(monkeypatch):
    fake = FakeMailcow(alias_record(private_comment="Orders and invoices"))

    with make_client(monkeypatch, fake) as client:
        response = client.post("/aliases/42/replace", data={"csrf_token": "test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["old_address"] == "amazon-k7@example.org"
    assert payload["address"].startswith("amazon-")
    suffix = payload["address"].split("@", 1)[0].rsplit("-", 1)[1]
    assert len(suffix) == 2
    assert fake.created == [
        {
            "address": payload["address"],
            "target": "hidden@example.org",
            "public_comment": "Amazon",
            "private_comment": "Orders and invoices",
            "sogo_visible": True,
        }
    ]
    assert fake.active_updates == [(42, False)]


def test_replace_alias_can_use_readable_random_format(monkeypatch):
    fake = FakeMailcow(alias_record(sogo_visible=False))
    monkeypatch.setattr(main_module, "readable_local_part", lambda _language: "river-moon-42")
    monkeypatch.setattr(
        alias_table_module,
        "readable_local_part",
        lambda _language: "river-moon-42",
    )

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases/42/replace",
            data={"csrf_token": "test", "mode": "readable"},
        )

    assert response.status_code == 200
    assert response.json()["address"] == "river-moon-42@example.org"
    assert fake.created == [
        {
            "address": "river-moon-42@example.org",
            "target": "hidden@example.org",
            "public_comment": "Amazon",
            "private_comment": "",
            "sogo_visible": False,
        }
    ]
    assert fake.active_updates == [(42, False)]


def test_replace_alias_can_use_custom_local_part(monkeypatch):
    fake = FakeMailcow(alias_record())

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases/42/replace",
            data={
                "csrf_token": "test",
                "mode": "custom",
                "local_part": "amazon-neu",
            },
        )

    assert response.status_code == 200
    assert response.json()["address"] == "amazon-neu@example.org"
    assert fake.created == [
        {
            "address": "amazon-neu@example.org",
            "target": "hidden@example.org",
            "public_comment": "Amazon",
            "private_comment": "",
            "sogo_visible": True,
        }
    ]
    assert fake.active_updates == [(42, False)]


def test_replace_alias_rejects_invalid_custom_local_part(monkeypatch):
    fake = FakeMailcow(alias_record())

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases/42/replace",
            data={
                "csrf_token": "test",
                "mode": "custom",
                "local_part": "Not Allowed!",
            },
        )

    assert response.status_code == 400
    assert fake.created == []
    assert fake.active_updates == []


def test_replace_alias_rejects_unknown_mode(monkeypatch):
    fake = FakeMailcow(alias_record())

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases/42/replace",
            data={"csrf_token": "test", "mode": "unknown"},
        )

    assert response.status_code == 400
    assert fake.created == []
    assert fake.active_updates == []


def test_replace_alias_reports_partial_result_when_old_alias_cannot_be_disabled(monkeypatch):
    fake = FakeMailcow(alias_record(), fail_disable=True)

    with make_client(monkeypatch, fake) as client:
        response = client.post("/aliases/42/replace", data={"csrf_token": "test"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "partial_replacement"
    assert detail["address"].startswith("amazon-")
    assert fake.active_updates == [(42, False)]


def test_primary_mailbox_alias_cannot_be_replaced(monkeypatch):
    primary = alias_record(
        address="hidden@example.org",
        goto="hidden@example.org",
        public_comment="",
        sogo_visible=False,
    )
    fake = FakeMailcow(primary)

    with make_client(monkeypatch, fake) as client:
        response = client.post("/aliases/42/replace", data={"csrf_token": "test"})

    assert response.status_code == 409
    assert fake.created == []
    assert fake.active_updates == []
