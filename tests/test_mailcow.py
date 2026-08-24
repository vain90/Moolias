import json
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import HTTPException

from moolias.config import Settings
from moolias.mailcow import MailcowClient


def settings(access_tag: str = "") -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_ACCESS_TAG=access_tag,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


async def test_get_mailbox_allows_every_mailbox_when_access_tag_is_empty():
    paths = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"username": "hidden@example.org", "domain": "example.org", "tags": []},
        )

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    mailbox = await client.get_mailbox("hidden@example.org")
    await client.close()

    assert mailbox["username"] == "hidden@example.org"
    assert paths == ["/api/v1/get/mailbox/hidden@example.org"]


async def test_get_mailbox_allows_matching_mailbox_tag_without_domain_lookup():
    paths = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "username": "hidden@example.org",
                "domain": "example.org",
                "tags": ["Moolias"],
            },
        )

    client = MailcowClient(settings("moolias"), transport=httpx.MockTransport(handler))
    mailbox = await client.get_mailbox("hidden@example.org")
    await client.close()

    assert mailbox["username"] == "hidden@example.org"
    assert paths == ["/api/v1/get/mailbox/hidden@example.org"]


async def test_get_mailbox_allows_matching_domain_tag():
    paths = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.startswith("/api/v1/get/mailbox/"):
            return httpx.Response(
                200,
                json={"username": "hidden@example.org", "domain": "example.org", "tags": []},
            )
        return httpx.Response(200, json={"domain_name": "example.org", "tags": ["moolias"]})

    client = MailcowClient(settings("moolias"), transport=httpx.MockTransport(handler))
    mailbox = await client.get_mailbox("hidden@example.org")
    await client.close()

    assert mailbox["username"] == "hidden@example.org"
    assert paths == [
        "/api/v1/get/mailbox/hidden@example.org",
        "/api/v1/get/domain/example.org",
    ]


async def test_get_mailbox_redirects_when_mailbox_and_domain_lack_access_tag():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/v1/get/mailbox/"):
            return httpx.Response(
                200,
                json={"username": "hidden@example.org", "domain": "example.org", "tags": ["other"]},
            )
        return httpx.Response(200, json={"domain_name": "example.org", "tags": []})

    client = MailcowClient(settings("moolias"), transport=httpx.MockTransport(handler))
    with pytest.raises(HTTPException) as exc_info:
        await client.get_mailbox("hidden@example.org")
    await client.close()

    assert exc_info.value.status_code == 303
    assert exc_info.value.headers == {"Location": "/?error=access-denied"}
    assert "moolias" in str(exc_info.value.detail)


async def test_create_alias_sets_name_private_description_sender_permission_and_sogo_visibility():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_added"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.create_alias(
        "amazon-k7p4@example.org",
        "hidden@example.org",
        "Amazon",
        private_comment="Invoices and Marketplace",
        sogo_visible=True,
    )
    await client.close()

    assert captured["path"] == "/api/v1/add/alias"
    assert captured["json"]["goto"] == "hidden@example.org"
    assert captured["json"]["public_comment"] == "Amazon"
    assert captured["json"]["private_comment"] == "Invoices and Marketplace"
    assert captured["json"]["sender_allowed"] == 1
    assert captured["json"]["sogo_visible"] == 1


async def test_reserved_alias_uses_private_marker_and_stays_hidden_from_sogo():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_added"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.create_alias(
        "pool-42@example.org",
        "hidden@example.org",
        private_comment="[moolias:reserved]",
        sogo_visible=False,
    )
    await client.close()

    assert captured["json"]["public_comment"] == ""
    assert captured["json"]["private_comment"] == "[moolias:reserved]"
    assert captured["json"]["sogo_visible"] == 0


async def test_alias_preferences_can_update_name_and_private_description_together():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.update_alias_preferences(
        42,
        "Amazon",
        True,
        private_comment="Invoices and AWS",
    )
    await client.close()

    assert captured["json"] == {
        "items": ["42"],
        "attr": {
            "public_comment": "Amazon",
            "sogo_visible": 1,
            "private_comment": "Invoices and AWS",
        },
    }


async def test_alias_preferences_leave_private_comment_untouched_when_not_supplied():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.update_alias_preferences(42, "Amazon shopping", True)
    await client.close()

    assert captured["json"] == {
        "items": ["42"],
        "attr": {
            "public_comment": "Amazon shopping",
            "sogo_visible": 1,
        },
    }


async def test_assign_reserved_alias_writes_prepared_private_comment():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.assign_reserved_alias(
        42,
        "Hotel",
        False,
        private_comment="Business trip",
    )
    await client.close()

    assert captured["json"] == {
        "items": ["42"],
        "attr": {
            "private_comment": "Business trip",
            "public_comment": "Hotel",
            "sogo_visible": 0,
        },
    }


async def test_mark_reserved_alias_used_preserves_human_private_comment_and_other_markers():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.content))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "address": "pool@example.org",
                    "goto": "hidden@example.org",
                    "domain": "example.org",
                    "active": "1",
                    "private_comment": (
                        "Hotel invoices [Family]\n"
                        "[moolias:reserved]\n"
                        "[moolias:future-state]"
                    ),
                    "public_comment": "",
                },
            )
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.mark_reserved_alias_used(42)
    await client.close()

    assert requests[0][0:2] == ("GET", "/api/v1/get/alias/42")
    payload = json.loads(requests[1][2])
    private_comment = payload["attr"]["private_comment"]
    assert "Hotel invoices [Family]" in private_comment
    assert "[moolias:reserved]" not in private_comment
    assert "[moolias:reserved-used]" in private_comment
    assert "[moolias:future-state]" in private_comment


async def test_set_active_many_updates_all_selected_aliases_in_one_request():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.set_active_many([12, 42, 77], False)
    await client.close()

    assert captured["path"] == "/api/v1/edit/alias"
    assert captured["json"] == {
        "items": ["12", "42", "77"],
        "attr": {"active": 0},
    }


async def test_set_sogo_visible_many_updates_all_selected_aliases_in_one_request():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.set_sogo_visible_many([12, 42], True)
    await client.close()

    assert captured["json"] == {
        "items": ["12", "42"],
        "attr": {"sogo_visible": 1},
    }


async def test_delete_alias_uses_mailcow_alias_delete_endpoint():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_deleted"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.delete_alias(42)
    await client.close()

    assert captured["path"] == "/api/v1/delete/alias"
    assert captured["form"]["items"] == ['["42"]']
