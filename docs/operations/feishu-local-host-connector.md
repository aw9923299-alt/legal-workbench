# Feishu Local Host Connector

This optional connector runs on the Mac host and reads only explicitly supported,
plaintext Feishu SQLite schemas. It does not mount `~/Library` into Docker, read
cookies, tokens, Keychain or credentials, inspect process memory, or attempt to
decrypt opaque databases.

The only supported local schema is `messages_v1`: a root-level `messages.db`
whose table set and column sets exactly match the versioned connector
fingerprint. Message-shaped tables at other paths, unknown versions, additional
columns, and partial schemas are refused.

Run a discovery-only report:

```bash
PYTHONPATH=apps/backend/src .venv/bin/python \
  -m legal_workbench.integrations.feishu_local_connector
```

Run unified ingestion for an existing Workbench OAuth authorization:

```bash
make feishu-local-sync \
  AUTHORIZATION_ID=<workbench-authorization-uuid> \
  ACCOUNT_ID_HASH=<sha256-of-explicitly-confirmed-local-account-id>
```

The host command uses the same PostgreSQL database configured by `.env`. Newly
discovered chats are `unapproved`; in particular, a new P2P scope remains
`disabled` and its records are stored with `store_only` until a human explicitly
allows collection. Message identity is `tenant_key + message_id`, and source
priority is `app_event > user_api > local_client`.

When readable records exist, `ACCOUNT_ID_HASH` is required as the operator's
explicit binding between one local Feishu account and the selected Workbench
OAuth authorization. Records from all other local accounts are ignored. If the
confirmed hash is absent or matches no readable records, sync fails closed
rather than guessing an identity mapping. It may be omitted only for the
`supported_but_no_readable_local_records` discovery result.

The default redacted artifact is `artifacts/feishu-local/host-sync.json`. When no
allowlisted plaintext message schema exists, the status is
`supported_but_no_readable_local_records`. This is a terminal supported state;
do not attempt to bypass client encryption.

An optional launchd template is available at
`deploy/launchd/com.legal-workbench.feishu-local-sync.plist.example`. Replace the
repository path, authorization UUID, and confirmed local account hash before
loading it.
