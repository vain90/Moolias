# Contributing to Moolias

Thanks for helping improve Moolias. Small, focused pull requests are easiest to review and maintain.

## Before you start

- Open an issue before large features or changes to the security or authorization model.
- Do not include real API keys, OAuth secrets, session secrets, mailbox addresses, private domains, or unredacted logs in issues, commits, or pull requests.
- Security vulnerabilities must not be reported in a public issue. Follow [SECURITY.md](SECURITY.md).

## Development setup

Python 3.12 or newer is required. The CI currently tests with Python 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
ruff check .
pytest -q
```

For container testing, use the explicit development Compose file:

```bash
docker compose -f compose.dev.yml build
docker compose -f compose.dev.yml up -d
```

`compose.local.yml` is intentionally not shipped by the repository. Operators may use that filename for deployment-specific overrides; `update.sh` layers it on top of `compose.yml` when present.

Never commit `.env`.

## Pull requests

1. Branch from the current `main` branch.
2. Keep each pull request focused on one change.
3. Add or update tests for behavior changes where practical.
4. Run `ruff check .` and `pytest -q` before submitting.
5. Explain any mailcow API, OAuth, permission, or ownership implications in the pull request.
6. Keep Moolias generic. Do not hard-code deployment-specific domains, mailbox names, IP addresses, or secrets.

Changes that affect alias ownership, OAuth, CSRF, sessions, the mailcow API key, private comments, or forwarding targets receive extra security review.

## Project principles

- mailcow remains the source of truth for alias data.
- Moolias does not maintain a second password database.
- A user may only manage aliases owned exclusively by their authenticated mailbox.
- Private mailcow admin comments remain private.
- Alias addresses are immutable after creation.

By submitting a contribution, you agree that your contribution is licensed under the project's MIT license.
