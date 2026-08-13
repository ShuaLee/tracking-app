import json

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from subscriptions.models import Subscription
from portfolios.models import Group, Portfolio
from users.models import User


PASSWORD = "A-strong-password-927!"
NEW_PASSWORD = "Another-strong-password-428!"


class JsonApiTestCase(TestCase):
    def post_json(self, name, data, **extra):
        return self.client.post(
            reverse(name),
            data=json.dumps(data),
            content_type="application/json",
            **extra,
        )

    def patch_json(self, name, data, **extra):
        return self.client.patch(
            reverse(name),
            data=json.dumps(data),
            content_type="application/json",
            **extra,
        )

    def delete_json(self, name, data, **extra):
        return self.client.delete(
            reverse(name),
            data=json.dumps(data),
            content_type="application/json",
            **extra,
        )

    def create_user(self, email="person@example.com"):
        user = User.objects.create_user(email, PASSWORD)
        user.profile.name = "Josh"
        user.profile.save()
        return user


class SignupApiTests(JsonApiTestCase):
    def test_signup_creates_account_dependencies_and_authenticates(self):
        response = self.post_json(
            "users:signup",
            {"email": "PERSON@example.com", "password": PASSWORD, "name": "Josh"},
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get()
        self.assertEqual(user.email, "person@example.com")
        self.assertEqual(user.profile.name, "Josh")
        self.assertEqual(user.subscription.plan, Subscription.Plan.FREE)
        self.assertEqual(user.subscription.status, Subscription.Status.ACTIVE)
        portfolio = Portfolio.objects.get(owner=user)
        self.assertEqual(portfolio.name, "My Portfolio")
        self.assertEqual(
            portfolio.groups.filter(
                mode=Group.Mode.SYSTEM, is_ungrouped=True
            ).count(),
            1,
        )
        self.assertEqual(str(user.pk), response.json()["user"]["id"])
        self.assertNotIn("password", response.content.decode().lower())
        self.assertEqual(str(user.pk), self.client.session["_auth_user_id"])

    def test_signup_rejects_duplicate_email_case_insensitively(self):
        self.create_user("person@example.com")

        response = self.post_json(
            "users:signup",
            {"email": "PERSON@EXAMPLE.COM", "password": PASSWORD},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["error"]["fields"])
        self.assertEqual(User.objects.count(), 1)

    def test_signup_rejects_missing_and_invalid_fields(self):
        response = self.post_json("users:signup", {"email": "bad"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.json()["error"]["fields"])

        response = self.post_json(
            "users:signup", {"email": "bad", "password": "password"}
        )
        self.assertIn("email", response.json()["error"]["fields"])
        self.assertIn("password", response.json()["error"]["fields"])

    def test_signup_requires_json(self):
        response = self.client.post(reverse("users:signup"), data={"email": "a@example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_json")

    def test_signup_rejects_non_string_email_and_name_without_server_error(self):
        response = self.post_json(
            "users:signup", {"email": 123, "password": PASSWORD, "name": ["Josh"]}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["error"]["fields"])
        self.assertIn("name", response.json()["error"]["fields"])

    def test_csrf_is_enforced_and_token_endpoint_bootstraps_client(self):
        client = Client(enforce_csrf_checks=True)
        payload = json.dumps({"email": "person@example.com", "password": PASSWORD})

        denied = client.post(
            reverse("users:signup"), payload, content_type="application/json"
        )
        self.assertEqual(denied.status_code, 403)

        token_response = client.get(reverse("users:csrf"))
        token = token_response.json()["csrfToken"]
        accepted = client.post(
            reverse("users:signup"),
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 201)


class AuthenticationApiTests(JsonApiTestCase):
    def setUp(self):
        self.user = self.create_user()

    def test_login_and_logout(self):
        response = self.post_json(
            "users:login", {"email": "PERSON@example.com", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)

        response = self.post_json("users:logout", {})
        self.assertEqual(response.status_code, 204)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_returns_generic_error_for_bad_password_and_unknown_email(self):
        bad_password = self.post_json(
            "users:login", {"email": self.user.email, "password": "wrong"}
        )
        unknown = self.post_json(
            "users:login", {"email": "missing@example.com", "password": "wrong"}
        )

        self.assertEqual(bad_password.status_code, 401)
        self.assertEqual(bad_password.json(), unknown.json())

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()

        response = self.post_json(
            "users:login", {"email": self.user.email, "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 401)

    def test_protected_endpoint_rejects_anonymous_user(self):
        response = self.client.get(reverse("users:me"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")


class CurrentUserApiTests(JsonApiTestCase):
    def setUp(self):
        self.user = self.create_user()
        self.other_user = self.create_user("other@example.com")
        self.client.force_login(self.user)

    def test_me_returns_only_current_users_safe_product_data(self):
        response = self.client.get(reverse("users:me"))

        self.assertEqual(response.status_code, 200)
        data = response.json()["user"]
        self.assertEqual(data["email"], self.user.email)
        self.assertEqual(data["profile"], {"name": "Josh"})
        self.assertEqual(data["subscription"], {"plan": "FREE", "status": "ACTIVE"})
        serialized = response.content.decode().lower()
        self.assertNotIn("password", serialized)
        self.assertNotIn(self.other_user.email, serialized)

    def test_patch_updates_name(self):
        response = self.patch_json("users:me", {"name": "  Joshua  "})

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.name, "Joshua")

    def test_email_change_requires_password_and_rejects_duplicate(self):
        missing_password = self.patch_json("users:me", {"email": "new@example.com"})
        self.assertEqual(missing_password.status_code, 400)
        self.assertIn("current_password", missing_password.json()["error"]["fields"])

        duplicate = self.patch_json(
            "users:me", {"email": self.other_user.email, "current_password": PASSWORD}
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("email", duplicate.json()["error"]["fields"])

        success = self.patch_json(
            "users:me", {"email": "NEW@example.com", "current_password": PASSWORD}
        )
        self.assertEqual(success.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    def test_email_can_be_resubmitted_unchanged(self):
        response = self.patch_json(
            "users:me", {"email": self.user.email, "current_password": PASSWORD}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], self.user.email)

    def test_public_profile_endpoint_cannot_change_subscription(self):
        response = self.patch_json("users:me", {"plan": "PRO"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.subscription.plan, Subscription.Plan.FREE)

    def test_account_deactivation_requires_password_and_preserves_data(self):
        denied = self.delete_json("users:me", {"current_password": "wrong"})
        self.assertEqual(denied.status_code, 403)

        response = self.delete_json("users:me", {"current_password": PASSWORD})
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(User.objects.filter(pk=self.user.pk, profile__isnull=False).exists())
        self.assertTrue(Subscription.objects.filter(user=self.user).exists())
        self.assertNotIn("_auth_user_id", self.client.session)


class PasswordApiTests(JsonApiTestCase):
    def setUp(self):
        self.user = self.create_user()

    def test_authenticated_password_change_keeps_session(self):
        self.client.force_login(self.user)

        response = self.post_json(
            "users:password-change",
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertEqual(self.client.get(reverse("users:me")).status_code, 200)

    def test_password_change_rejects_wrong_current_and_weak_new_password(self):
        self.client.force_login(self.user)

        wrong = self.post_json(
            "users:password-change",
            {"current_password": "wrong", "new_password": NEW_PASSWORD},
        )
        weak = self.post_json(
            "users:password-change",
            {"current_password": PASSWORD, "new_password": "password"},
        )

        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(weak.status_code, 400)

    @override_settings(
        MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    )
    def test_reset_request_sends_message_without_enumerating_accounts(self):
        existing = self.post_json("users:password-reset", {"email": self.user.email})
        missing = self.post_json("users:password-reset", {"email": "missing@example.com"})

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(existing.json(), missing.json())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset-password?uid=", mail.outbox[0].body)
        self.assertIn("token=", mail.outbox[0].body)

    def test_reset_confirm_accepts_valid_token_once(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.post_json(
            "users:password-reset-confirm",
            {"uid": uid, "token": token, "new_password": NEW_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

        reused = self.post_json(
            "users:password-reset-confirm",
            {"uid": uid, "token": token, "new_password": PASSWORD},
        )
        self.assertEqual(reused.status_code, 400)
        self.assertEqual(reused.json()["error"]["code"], "invalid_reset_token")

    def test_reset_confirm_rejects_invalid_token(self):
        response = self.post_json(
            "users:password-reset-confirm",
            {"uid": "invalid", "token": "invalid", "new_password": NEW_PASSWORD},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_reset_token")


class SubscriptionApiTests(JsonApiTestCase):
    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)

    def test_subscription_and_entitlements_endpoints(self):
        subscription_response = self.client.get(reverse("users:subscription"))
        entitlement_response = self.client.get(reverse("users:entitlements"))

        self.assertEqual(
            subscription_response.json()["subscription"],
            {"plan": "FREE", "status": "ACTIVE"},
        )
        entitlements = entitlement_response.json()["entitlements"]
        self.assertFalse(entitlements["capabilities"]["brokerage_sync"])
        self.assertEqual(entitlements["limits"]["portfolios"], 1)
