from copy import deepcopy

from django.conf import settings

from .models import Subscription


DEFAULT_POLICY = {
    Subscription.Plan.FREE: {
        "capabilities": {
            "brokerage_sync": False,
            "advanced_sheets": False,
            "professional_features": False,
        },
        "limits": {"portfolios": 1, "holdings": 25},
    },
    Subscription.Plan.PRO: {
        "capabilities": {
            "brokerage_sync": True,
            "advanced_sheets": True,
            "professional_features": False,
        },
        "limits": {"portfolios": 1, "holdings": None},
    },
    Subscription.Plan.MANAGER: {
        "capabilities": {
            "brokerage_sync": True,
            "advanced_sheets": True,
            "professional_features": False,
        },
        "limits": {"portfolios": None, "holdings": None},
    },
}


def _policy():
    policy = deepcopy(DEFAULT_POLICY)
    configured = getattr(settings, "ENTITLEMENT_POLICY", {})
    for plan, values in configured.items():
        target = policy.setdefault(plan, {"capabilities": {}, "limits": {}})
        target["capabilities"].update(values.get("capabilities", {}))
        target["limits"].update(values.get("limits", {}))
    return policy


def _active_subscription(user):
    if not user.is_active:
        return None
    subscription = user.subscription
    if subscription.status != Subscription.Status.ACTIVE:
        return None
    return subscription


def has(user, capability):
    subscription = _active_subscription(user)
    if subscription is None:
        return False
    return bool(
        _policy().get(subscription.plan, {}).get("capabilities", {}).get(capability, False)
    )


def limit(user, resource):
    subscription = _active_subscription(user)
    if subscription is None:
        return 0
    return _policy().get(subscription.plan, {}).get("limits", {}).get(resource, 0)


def entitlements_for(user):
    subscription = _active_subscription(user)
    if subscription is None:
        return {"capabilities": {}, "limits": {}}
    plan_policy = _policy().get(subscription.plan, {"capabilities": {}, "limits": {}})
    return {
        "capabilities": dict(plan_policy["capabilities"]),
        "limits": dict(plan_policy["limits"]),
    }

