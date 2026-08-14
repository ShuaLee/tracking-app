import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from integrations.brokerage.contracts import ConnectionPortal
from integrations.brokerage.models import BrokerageConnection
from portfolios.tests.factories import portfolio, user
from subscriptions.models import Subscription


class BrokerageApiTests(TestCase):
    def post_json(self, name, body, *, args=()):
        return self.client.post(
            reverse(name, args=args),
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_free_plan_cannot_start_brokerage_flow(self):
        owner = user()
        self.client.force_login(owner)

        response = self.post_json(
            "brokerage:portal", {"portfolio_id": str(portfolio(owner).pk)}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "entitlement_required")

    @patch("integrations.brokerage.views.create_portal")
    def test_pro_plan_can_create_portal_without_secret_exposure(self, create_portal):
        owner = user(plan=Subscription.Plan.PRO)
        target = portfolio(owner)
        self.client.force_login(owner)
        create_portal.return_value = ConnectionPortal("https://connect.example/portal")

        response = self.post_json(
            "brokerage:portal", {"portfolio_id": str(target.pk)}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"redirect_url": "https://connect.example/portal"})
        self.assertNotIn("secret", response.content.decode().lower())

    def test_connection_endpoints_are_owner_scoped(self):
        owner = user(plan=Subscription.Plan.PRO)
        other = user("other-api@example.com", plan=Subscription.Plan.PRO)
        connection = BrokerageConnection.objects.create(
            user=other,
            portfolio=portfolio(other),
            provider_connection_id="connection-1",
            name="Other broker",
        )
        self.client.force_login(owner)

        response = self.post_json("brokerage:sync", {}, args=[connection.pk])

        self.assertEqual(response.status_code, 404)
