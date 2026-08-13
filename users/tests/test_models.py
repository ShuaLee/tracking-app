from django.core.exceptions import ValidationError
from django.test import TestCase

from subscriptions.models import Subscription
from users.models import Profile, User


class UserManagerTests(TestCase):
    def test_create_user_normalizes_email_and_hashes_password(self):
        user = User.objects.create_user("  PERSON@Example.COM  ", "A-strong-password-927!")

        self.assertEqual(user.email, "person@example.com")
        self.assertTrue(user.check_password("A-strong-password-927!"))
        self.assertNotEqual(user.password, "A-strong-password-927!")

    def test_create_user_requires_email(self):
        with self.assertRaisesMessage(ValueError, "email address is required"):
            User.objects.create_user("", "A-strong-password-927!")

    def test_create_superuser_sets_required_flags(self):
        user = User.objects.create_superuser("admin@example.com", "A-strong-password-927!")

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_superuser_rejects_invalid_flags_and_missing_password(self):
        with self.assertRaisesMessage(ValueError, "is_staff=True"):
            User.objects.create_superuser(
                "admin@example.com", "A-strong-password-927!", is_staff=False
            )
        with self.assertRaisesMessage(ValueError, "must have a password"):
            User.objects.create_superuser("admin@example.com", None)

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(ValidationError):
            User.objects.create_user("not-an-email", "A-strong-password-927!")


class AccountDependencyTests(TestCase):
    def test_new_user_gets_exactly_one_profile_and_subscription(self):
        user = User.objects.create_user("person@example.com", "A-strong-password-927!")

        self.assertEqual(Profile.objects.filter(user=user).count(), 1)
        self.assertEqual(Subscription.objects.filter(user=user).count(), 1)
        self.assertEqual(user.subscription.plan, Subscription.Plan.FREE)
        self.assertEqual(user.subscription.status, Subscription.Status.ACTIVE)

        user.email = "updated@example.com"
        user.save()
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)
        self.assertEqual(Subscription.objects.filter(user=user).count(), 1)

    def test_deleting_user_cascades_stage_one_dependencies(self):
        user = User.objects.create_user("person@example.com", "A-strong-password-927!")
        profile_id = user.profile_id if hasattr(user, "profile_id") else user.profile.pk
        subscription_id = user.subscription.pk

        user.delete()

        self.assertFalse(Profile.objects.filter(pk=profile_id).exists())
        self.assertFalse(Subscription.objects.filter(pk=subscription_id).exists())

