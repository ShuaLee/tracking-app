from django.test import TestCase, override_settings

from subscriptions.entitlements import entitlements_for, has, limit
from subscriptions.models import Subscription
from subscriptions.services import change_subscription
from users.models import User


class EntitlementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "person@example.com", "A-strong-password-927!"
        )

    def test_free_policy(self):
        self.assertFalse(has(self.user, "brokerage_sync"))
        self.assertFalse(has(self.user, "advanced_sheets"))
        self.assertEqual(limit(self.user, "portfolios"), 1)
        self.assertEqual(limit(self.user, "holdings"), 25)

    def test_pro_policy(self):
        change_subscription(subscription=self.user.subscription, plan=Subscription.Plan.PRO)

        self.assertTrue(has(self.user, "brokerage_sync"))
        self.assertTrue(has(self.user, "advanced_sheets"))
        self.assertEqual(limit(self.user, "portfolios"), 1)
        self.assertIsNone(limit(self.user, "holdings"))

    def test_manager_value_does_not_enable_unimplemented_professional_features(self):
        change_subscription(subscription=self.user.subscription, plan=Subscription.Plan.MANAGER)

        self.assertTrue(has(self.user, "brokerage_sync"))
        self.assertFalse(has(self.user, "professional_features"))
        self.assertIsNone(limit(self.user, "portfolios"))

    def test_inactive_subscription_has_no_capabilities_or_limits(self):
        change_subscription(
            subscription=self.user.subscription,
            status=Subscription.Status.CANCELED,
        )

        self.assertFalse(has(self.user, "brokerage_sync"))
        self.assertEqual(limit(self.user, "portfolios"), 0)
        self.assertEqual(entitlements_for(self.user), {"capabilities": {}, "limits": {}})

    def test_inactive_user_has_no_entitlements(self):
        self.user.is_active = False
        self.user.save()

        self.assertFalse(has(self.user, "brokerage_sync"))
        self.assertEqual(limit(self.user, "holdings"), 0)

    def test_unknown_capability_and_limit_are_denied(self):
        self.assertFalse(has(self.user, "unknown"))
        self.assertEqual(limit(self.user, "unknown"), 0)

    @override_settings(
        ENTITLEMENT_POLICY={
            "FREE": {
                "capabilities": {"brokerage_sync": True},
                "limits": {"holdings": 50},
            }
        }
    )
    def test_policy_can_be_overridden_centrally(self):
        self.assertTrue(has(self.user, "brokerage_sync"))
        self.assertEqual(limit(self.user, "holdings"), 50)

