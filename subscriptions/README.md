# Subscriptions application

Owns plan state and the centralized entitlement vocabulary. `entitlements.py` answers capability and limit questions; callers should use it instead of branching directly on plan names. `services.py` manages subscription state without owning provider-specific billing behavior.
