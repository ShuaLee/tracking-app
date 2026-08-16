# Brokerage integration

- `contracts.py`: normalized brokerage accounts and positions.
- `service.py`: provider-neutral connection operations.
- `models.py`: encrypted provider-user and connection persistence.
- `sync.py`: idempotent reconciliation into synced portfolio Groups and Holdings.
- `providers/`: provider adapters; currently SnapTrade.
- `api` boundary: `views.py`, `serializers.py`, and `urls.py`.

Brokerage providers control synced position state. Disconnecting preserves imported portfolio history.
