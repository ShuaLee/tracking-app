from unittest.mock import patch

from django.test import TestCase

from portfolios.models import Portfolio
from users.models import User
from users.services import AccountValidationError, create_account, deactivate_account


class AccountServiceTests(TestCase):
    def test_create_account_sets_profile_name(self):
        user = create_account(
            email="PERSON@example.com",
            password="A-strong-password-927!",
            name="  Josh  ",
        )

        self.assertEqual(user.email, "person@example.com")
        self.assertEqual(user.profile.name, "Josh")
        self.assertEqual(Portfolio.objects.filter(owner=user).count(), 1)

    def test_create_account_validates_password(self):
        with self.assertRaises(AccountValidationError) as context:
            create_account(email="person@example.com", password="password", name="Josh")

        self.assertIn("password", context.exception.errors)
        self.assertFalse(User.objects.exists())

    def test_create_account_rolls_back_if_dependency_creation_fails(self):
        with patch(
            "users.signals.Subscription.objects.create",
            side_effect=RuntimeError("subscription failure"),
        ):
            with self.assertRaisesMessage(RuntimeError, "subscription failure"):
                create_account(
                    email="person@example.com",
                    password="A-strong-password-927!",
                    name="Josh",
                )

        self.assertFalse(User.objects.filter(email="person@example.com").exists())

    def test_create_account_rolls_back_if_portfolio_bootstrap_fails(self):
        with patch(
            "portfolios.services.Group.objects.create",
            side_effect=RuntimeError("group failure"),
        ):
            with self.assertRaisesMessage(RuntimeError, "group failure"):
                create_account(
                    email="person@example.com",
                    password="A-strong-password-927!",
                    name="Josh",
                )

        self.assertFalse(User.objects.filter(email="person@example.com").exists())
        self.assertFalse(Portfolio.objects.exists())

    def test_deactivate_account_preserves_related_records(self):
        user = create_account(
            email="person@example.com",
            password="A-strong-password-927!",
            name="Josh",
        )

        deactivate_account(user=user)

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(hasattr(user, "profile"))
        self.assertTrue(hasattr(user, "subscription"))
