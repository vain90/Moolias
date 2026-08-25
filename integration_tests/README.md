# Real Mailcow integration tests

These tests validate Moolias's external Mailcow API contracts against a fresh disposable Mailcow stack. They do not use production credentials, DNS records, mailboxes, aliases, or data.

## What is covered

The suite currently verifies:

- profile mailbox lookup and domain-level Moolias access tags
- alias create/read/edit/disable/delete behavior
- public and private alias comments
- `sogo_visible` and `sender_allowed` fields
- `[moolias:reserved]` and `[moolias:reserved-used]` marker round-trips
- mailbox tag add/remove behavior through the endpoints Moolias uses
- statistics-mode tag replacement while unrelated tags are preserved
- authenticated access to the Rspamd history endpoint
- installation of the restricted Newsletter Agent
- remote Dovecot `doveadm` header lookup through Mailcow nginx using a real disposable mailbox and message

OAuth browser login is not part of this suite because the disposable Mailcow has no configured external OAuth identity provider. The Rspamd check validates the real endpoint and response contract; generating representative Rspamd newsletter classifications is intentionally left out because the fixture does not have deterministic public DNS/DKIM identities.

The Newsletter Agent integration does create a synthetic message directly in the disposable Dovecot mailbox. It validates the Mailcow Dovecot listener, installer-managed authentication, sidecar, nginx route, HMAC request authentication and the exact header response used by Moolias.

## GitHub Actions

`Mailcow integration` is a separate workflow. It runs:

- manually through **Run workflow**
- when called by another workflow, for example a future release gate
- on pull requests that change the integration-test infrastructure or Mailcow-facing Moolias components

The workflow starts Mailcow on the GitHub-hosted runner, runs `pytest -q integration_tests`, uploads diagnostics on failure, and always removes the Mailcow containers and volumes afterwards.

## Local execution

Docker with the Compose plugin, Git, curl, jq, Python 3.12+ and the Moolias development dependencies are required. The helper clones a fresh `mailcow/mailcow-dockerized` checkout into `/tmp` and removes all containers and volumes when it exits.

From the repository root:

```bash
python -m pip install -e '.[dev]'
MAILCOW_READY_COMMAND='pytest -q integration_tests' \
  bash .github/scripts/mailcow-feasibility.sh
```

The disposable web/API endpoint binds to `127.0.0.1:8080`. The helper uses the reserved hostname `mail.mailcow-ci.test`, injects a temporary API key, and exports `MAILCOW_URL` plus `MAILCOW_API_KEY` to the test command.

The Newsletter Agent test builds a local Moolias image when `MOOLIAS_AGENT_IMAGE` does not already exist. GitHub Actions prebuilds and reuses the image for the complete integration matrix.

Do not point these tests at a production Mailcow instance.
