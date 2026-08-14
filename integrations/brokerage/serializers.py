def connection_data(connection):
    return {
        "id": str(connection.id),
        "portfolio_id": str(connection.portfolio_id),
        "provider": connection.provider,
        "provider_connection_id": connection.provider_connection_id,
        "name": connection.name,
        "institution": connection.institution,
        "brokerage_slug": connection.brokerage_slug,
        "status": connection.status,
        "last_synced_at": (
            connection.last_synced_at.isoformat() if connection.last_synced_at else None
        ),
        "last_error_code": connection.last_error_code or None,
        "metadata": connection.metadata,
    }
