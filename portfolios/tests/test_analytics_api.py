"""API tests for portfolio analytics and configurable views."""

import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from portfolios.models import IncomeRule, Theme
from portfolios.services.holdings import create_manual_holding
from portfolios.tests.factories import asset_type, portfolio, user
from subscriptions.models import Subscription


class Stage5ApiTests(TestCase):
    def post(self, name, body, *args):
        return self.client.post(
            reverse(name, args=args),
            data=json.dumps(body),
            content_type="application/json",
        )

    def patch(self, name, body, *args):
        return self.client.patch(
            reverse(name, args=args),
            data=json.dumps(body),
            content_type="application/json",
        )

    def setUp(self):
        self.owner = user(plan=Subscription.Plan.PRO)
        self.portfolio = portfolio(self.owner)
        self.holding = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type("Other"),
            name="Rental",
            native_currency="USD",
            country_code="US",
            manual_value="1000",
        )
        self.client.force_login(self.owner)

    def test_free_plan_is_denied_without_creating_a_view(self):
        free = user("free-analytics-api@example.com")
        target = portfolio(free)
        self.client.force_login(free)

        response = self.post("portfolios:views", {"name": "Nope"}, target.pk)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "entitlement_required")
        self.assertFalse(target.saved_views.exists())

    def test_create_blank_and_template_views_without_permanent_theme_or_income(self):
        blank = self.post(
            "portfolios:views", {"name": "Anything I Want"}, self.portfolio.pk
        )
        template = self.post(
            "portfolios:views",
            {"name": "My Theme Setup", "template": "themes"},
            self.portfolio.pk,
        )

        self.assertEqual(blank.status_code, 201)
        self.assertEqual(blank.json()["view"]["blocks"], [])
        self.assertEqual(template.status_code, 201)
        self.assertEqual(len(template.json()["view"]["blocks"]), 2)
        self.assertFalse(Theme.objects.exists())
        self.assertFalse(IncomeRule.objects.exists())

    def test_builder_schema_is_discoverable(self):
        response = self.client.get(reverse("portfolios:view-schema"))

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(
            set(schema["data_sources"]), {"HOLDINGS", "INCOME", "THEMES", "GROUPS"}
        )
        self.assertEqual(set(schema["presentations"]), {"TABLE", "LIST", "SUMMARY"})
        self.assertEqual(set(schema["scope_modes"]), {"ALL", "SELECTED"})
        self.assertEqual(schema["maximum_group_fields"], 3)
        self.assertTrue(schema["can_copy_existing_view"])
        self.assertIn("country", {
            field["name"] for field in schema["data_sources"]["HOLDINGS"]
        })

    def test_complete_theme_income_and_custom_view_flow(self):
        theme_response = self.post(
            "portfolios:themes",
            {"name": "Real Estate", "target_percentage": "25"},
            self.portfolio.pk,
        )
        theme_id = theme_response.json()["theme"]["id"]
        assignment = self.post(
            "portfolios:theme-assignments",
            {"holding_id": str(self.holding.pk)},
            self.portfolio.pk,
            theme_id,
        )
        income = self.post(
            "portfolios:income-rules",
            {
                "holding_id": str(self.holding.pk),
                "name": "Rent",
                "category": "RENT",
                "amount_per_payment": "100",
                "currency": "USD",
                "frequency": "MONTHLY",
            },
            self.portfolio.pk,
        )
        view_response = self.post(
            "portfolios:views", {"name": "Custom Yield"}, self.portfolio.pk
        )
        view_id = view_response.json()["view"]["id"]
        block = self.post(
            "portfolios:view-blocks",
            {
                "title": "Yield list",
                "data_source": "HOLDINGS",
                "presentation": "TABLE",
                "configuration": {
                    "fields": ["asset_name", "theme", "annual_income", "current_yield"]
                },
            },
            self.portfolio.pk,
            view_id,
        )
        rendered = self.client.get(
            reverse("portfolios:view-render", args=[self.portfolio.pk, view_id])
        )

        self.assertEqual(theme_response.status_code, 201)
        self.assertEqual(assignment.status_code, 201)
        self.assertEqual(income.status_code, 201)
        self.assertEqual(block.status_code, 201)
        self.assertEqual(rendered.status_code, 200)
        row = rendered.json()["view"]["blocks"][0]["result"]["rows"][0]
        self.assertEqual(row["asset_name"], "Rental")
        self.assertEqual(row["theme"], "Real Estate")
        self.assertEqual(row["annual_income"], "1200.00")
        overview = self.client.get(
            reverse("portfolios:overview", args=[self.portfolio.pk])
        ).json()["overview"]
        self.assertEqual(overview["expected_annual_income"], "1200.00")
        self.assertEqual(Decimal(overview["current_yield"]), Decimal("120"))

    def test_invalid_block_configuration_is_rejected(self):
        view = self.post(
            "portfolios:views", {"name": "Safe"}, self.portfolio.pk
        ).json()["view"]

        response = self.post(
            "portfolios:view-blocks",
            {
                "data_source": "HOLDINGS",
                "presentation": "TABLE",
                "configuration": {"fields": ["asset_name", "secret_database_column"]},
            },
            self.portfolio.pk,
            view["id"],
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("configuration", response.json()["error"]["fields"])

    def test_cross_user_view_is_not_visible(self):
        other = user("other-analytics@example.com", plan=Subscription.Plan.PRO)
        other_portfolio = portfolio(other)
        self.client.force_login(other)
        other_view = self.post(
            "portfolios:views", {"name": "Other"}, other_portfolio.pk
        ).json()["view"]
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse(
                "portfolios:view-detail",
                args=[self.portfolio.pk, other_view["id"]],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_selected_country_view_and_view_duplication(self):
        excluded = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type("Other"),
            name="Excluded Canadian Asset",
            native_currency="USD",
            country_code="CA",
            manual_value="900",
        )
        created = self.post(
            "portfolios:views",
            {
                "name": "Selected Countries",
                "template": "country",
                "scope_mode": "SELECTED",
                "holding_ids": [str(self.holding.pk)],
            },
            self.portfolio.pk,
        )
        view = created.json()["view"]
        rendered = self.client.get(
            reverse("portfolios:view-render", args=[self.portfolio.pk, view["id"]])
        ).json()["view"]
        copied = self.post(
            "portfolios:views",
            {"name": "Country Copy", "source_view_id": view["id"]},
            self.portfolio.pk,
        )

        rows = rendered["blocks"][0]["result"]["rows"]
        self.assertEqual(rows[0]["country"], "US")
        self.assertEqual(rows[0]["sum_value"], "1000.00")
        self.assertNotIn(str(excluded.pk), view["holding_ids"])
        self.assertEqual(copied.status_code, 201)
        self.assertEqual(copied.json()["view"]["scope_mode"], "SELECTED")
        self.assertEqual(copied.json()["view"]["holding_ids"], [str(self.holding.pk)])
        self.assertEqual(len(copied.json()["view"]["blocks"]), 1)

        all_assets_copy = self.post(
            "portfolios:views",
            {
                "name": "All Country Assets",
                "source_view_id": view["id"],
                "scope_mode": "ALL",
            },
            self.portfolio.pk,
        )
        self.assertEqual(all_assets_copy.status_code, 201)
        self.assertEqual(all_assets_copy.json()["view"]["scope_mode"], "ALL")
        self.assertEqual(all_assets_copy.json()["view"]["holding_ids"], [])

    def test_asset_classification_can_be_managed_for_view_grouping(self):
        updated = self.patch(
            "portfolios:holding-classification",
            {"country_code": "ca", "sector": "Property", "industry": "REIT"},
            self.portfolio.pk,
            self.holding.pk,
        )
        invalid = self.patch(
            "portfolios:holding-classification",
            {"country_code": "Canada"},
            self.portfolio.pk,
            self.holding.pk,
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["asset"]["country_code"], "CA")
        self.assertEqual(updated.json()["asset"]["sector"], "Property")
        self.assertEqual(updated.json()["asset"]["industry"], "REIT")
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("country_code", invalid.json()["error"]["fields"])
