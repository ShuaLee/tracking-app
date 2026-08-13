import json

from django.test import TestCase, override_settings
from django.urls import reverse

from portfolios.models import Asset, AssetType, Group, Holding, Portfolio
from portfolios.services import create_manual_group, create_manual_holding, create_portfolio

from .factories import PASSWORD, asset_type, user


class PortfolioApiTestCase(TestCase):
    def post_json(self, name, data, *, args=()):
        return self.client.post(
            reverse(name, args=args),
            json.dumps(data),
            content_type="application/json",
        )

    def patch_json(self, name, data, *, args=()):
        return self.client.patch(
            reverse(name, args=args),
            json.dumps(data),
            content_type="application/json",
        )

    def delete_json(self, name, *, args=()):
        return self.client.delete(
            reverse(name, args=args),
            data=json.dumps({}),
            content_type="application/json",
        )

    def setUp(self):
        self.user = user()
        self.other = user("other@example.com")
        self.client.force_login(self.user)


class PortfolioApiTests(PortfolioApiTestCase):
    def test_create_list_read_update_and_delete_portfolio(self):
        created = self.post_json(
            "portfolios:list", {"name": "Wealth", "base_currency": "cad"}
        )
        self.assertEqual(created.status_code, 201)
        portfolio_id = created.json()["portfolio"]["id"]
        self.assertEqual(created.json()["portfolio"]["base_currency"], "CAD")
        portfolio = Portfolio.objects.get(pk=portfolio_id)
        self.assertEqual(portfolio.groups.filter(is_ungrouped=True).count(), 1)

        listed = self.client.get(reverse("portfolios:list"))
        self.assertEqual(len(listed.json()["portfolios"]), 1)
        read = self.client.get(reverse("portfolios:detail", args=[portfolio_id]))
        self.assertEqual(read.status_code, 200)

        updated = self.patch_json(
            "portfolios:detail", {"name": "Family Wealth"}, args=[portfolio_id]
        )
        self.assertEqual(updated.json()["portfolio"]["name"], "Family Wealth")

        deleted = self.delete_json("portfolios:detail", args=[portfolio_id])
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Portfolio.objects.filter(pk=portfolio_id).exists())

    def test_free_plan_cannot_create_second_portfolio(self):
        create_portfolio(owner=self.user, name="First")
        response = self.post_json("portfolios:list", {"name": "Second"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "entitlement_limit_reached")

    def test_anonymous_and_cross_user_access_are_denied(self):
        other_portfolio = create_portfolio(owner=self.other, name="Private")
        response = self.client.get(reverse("portfolios:detail", args=[other_portfolio.pk]))
        self.assertEqual(response.status_code, 404)

        self.client.logout()
        response = self.client.get(reverse("portfolios:list"))
        self.assertEqual(response.status_code, 401)

    def test_unknown_fields_are_rejected(self):
        response = self.post_json("portfolios:list", {"name": "Mine", "owner": str(self.other.pk)})
        self.assertEqual(response.status_code, 400)
        self.assertIn("owner", response.json()["error"]["fields"])


class GroupApiTests(PortfolioApiTestCase):
    def setUp(self):
        super().setUp()
        self.portfolio = create_portfolio(owner=self.user, name="Mine")

    def test_manual_group_crud_and_system_group_protection(self):
        created = self.post_json(
            "portfolios:groups", {"name": "Cars"}, args=[self.portfolio.pk]
        )
        self.assertEqual(created.status_code, 201)
        group_id = created.json()["group"]["id"]
        self.assertEqual(created.json()["group"]["mode"], "MANUAL")

        listed = self.client.get(reverse("portfolios:groups", args=[self.portfolio.pk]))
        self.assertEqual(len(listed.json()["groups"]), 2)

        renamed = self.patch_json(
            "portfolios:group-detail",
            {"name": "Vehicles"},
            args=[self.portfolio.pk, group_id],
        )
        self.assertEqual(renamed.json()["group"]["name"], "Vehicles")
        self.assertEqual(
            self.delete_json(
                "portfolios:group-detail", args=[self.portfolio.pk, group_id]
            ).status_code,
            204,
        )

        system = self.portfolio.groups.get(is_ungrouped=True)
        protected = self.delete_json(
            "portfolios:group-detail", args=[self.portfolio.pk, system.pk]
        )
        self.assertEqual(protected.status_code, 400)
        self.assertEqual(protected.json()["error"]["code"], "protected_operation")

    def test_group_delete_moves_holdings_to_ungrouped(self):
        group = create_manual_group(portfolio=self.portfolio, name="Cars")
        holding = create_manual_holding(
            portfolio=self.portfolio,
            group=group,
            asset_type=asset_type("Car"),
            name="Car",
        )
        response = self.delete_json(
            "portfolios:group-detail", args=[self.portfolio.pk, group.pk]
        )
        self.assertEqual(response.status_code, 204)
        holding.refresh_from_db()
        self.assertTrue(holding.group.is_ungrouped)

    def test_cannot_access_group_through_another_portfolio(self):
        other_portfolio = create_portfolio(owner=self.other, name="Other")
        group = other_portfolio.groups.get(is_ungrouped=True)
        response = self.client.get(
            reverse("portfolios:group-detail", args=[self.portfolio.pk, group.pk])
        )
        self.assertEqual(response.status_code, 404)


class AssetTypeApiTests(PortfolioApiTestCase):
    def test_lists_builtins_and_only_current_users_custom_types(self):
        own = AssetType.objects.create(
            owner=self.user,
            name="Pokemon Card",
            system_category=AssetType.Category.COLLECTIBLE,
        )
        AssetType.objects.create(
            owner=self.other,
            name="Other Private Type",
            system_category=AssetType.Category.OTHER,
        )
        response = self.client.get(reverse("portfolios:asset-types"))
        ids = {item["id"] for item in response.json()["asset_types"]}
        self.assertIn(str(own.pk), ids)
        self.assertNotIn(
            str(self.other.custom_asset_types.get().pk), ids
        )
        self.assertTrue(any(item["is_system"] for item in response.json()["asset_types"]))

    def test_custom_type_crud_and_builtin_protection(self):
        created = self.post_json(
            "portfolios:asset-types",
            {"name": "Gold Bars", "system_category": "COMMODITY"},
        )
        self.assertEqual(created.status_code, 201)
        type_id = created.json()["asset_type"]["id"]
        updated = self.patch_json(
            "portfolios:asset-type-detail",
            {"name": "Physical Gold"},
            args=[type_id],
        )
        self.assertEqual(updated.json()["asset_type"]["name"], "Physical Gold")
        self.assertEqual(
            self.delete_json("portfolios:asset-type-detail", args=[type_id]).status_code,
            204,
        )

        builtin = asset_type("Stock")
        response = self.patch_json(
            "portfolios:asset-type-detail", {"name": "Changed"}, args=[builtin.pk]
        )
        self.assertEqual(response.status_code, 400)

    def test_other_users_custom_type_is_not_found(self):
        private = AssetType.objects.create(
            owner=self.other,
            name="Private",
            system_category=AssetType.Category.OTHER,
        )
        response = self.client.get(
            reverse("portfolios:asset-type-detail", args=[private.pk])
        )
        self.assertEqual(response.status_code, 404)


class HoldingApiTests(PortfolioApiTestCase):
    def setUp(self):
        super().setUp()
        self.portfolio = create_portfolio(owner=self.user, name="Mine", base_currency="CAD")
        self.cars = create_manual_group(portfolio=self.portfolio, name="Cars")

    def holding_payload(self, **overrides):
        payload = {
            "name": "Porsche",
            "asset_type_id": str(asset_type("Car").pk),
            "group_id": str(self.cars.pk),
            "native_currency": "CAD",
            "metadata": {"year": 2024},
            "quantity": "1",
            "average_cost": "80000",
            "cost_currency": "CAD",
            "manual_value": "90000",
        }
        payload.update(overrides)
        return payload

    def test_create_list_read_update_move_and_delete_manual_holding(self):
        created = self.post_json(
            "portfolios:holdings",
            self.holding_payload(),
            args=[self.portfolio.pk],
        )
        self.assertEqual(created.status_code, 201)
        holding_id = created.json()["holding"]["id"]
        self.assertEqual(created.json()["holding"]["cost_basis"], "80000")
        self.assertEqual(created.json()["holding"]["gain_loss"], "10000")

        listed = self.client.get(reverse("portfolios:holdings", args=[self.portfolio.pk]))
        self.assertEqual(len(listed.json()["holdings"]), 1)
        read = self.client.get(
            reverse("portfolios:holding-detail", args=[self.portfolio.pk, holding_id])
        )
        self.assertEqual(read.status_code, 200)

        ungrouped = self.portfolio.groups.get(is_ungrouped=True)
        updated = self.patch_json(
            "portfolios:holding-detail",
            {"name": "Porsche 911", "group_id": str(ungrouped.pk), "manual_value": "95000"},
            args=[self.portfolio.pk, holding_id],
        )
        self.assertEqual(updated.json()["holding"]["asset"]["name"], "Porsche 911")
        self.assertTrue(updated.json()["holding"]["group"]["is_ungrouped"])

        deleted = self.delete_json(
            "portfolios:holding-detail", args=[self.portfolio.pk, holding_id]
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Holding.objects.filter(pk=holding_id).exists())

    def test_omitted_group_assigns_ungrouped(self):
        payload = self.holding_payload()
        payload.pop("group_id")
        response = self.post_json(
            "portfolios:holdings", payload, args=[self.portfolio.pk]
        )
        self.assertTrue(response.json()["holding"]["group"]["is_ungrouped"])

    def test_duplicate_holdings_are_accepted(self):
        first = self.post_json(
            "portfolios:holdings", self.holding_payload(), args=[self.portfolio.pk]
        )
        second = self.post_json(
            "portfolios:holdings", self.holding_payload(), args=[self.portfolio.pk]
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

    def test_cross_portfolio_group_and_custom_type_are_rejected(self):
        other_portfolio = create_portfolio(owner=self.other, name="Other")
        response = self.post_json(
            "portfolios:holdings",
            self.holding_payload(group_id=str(other_portfolio.groups.get(is_ungrouped=True).pk)),
            args=[self.portfolio.pk],
        )
        self.assertEqual(response.status_code, 400)

        private_type = AssetType.objects.create(
            owner=self.other, name="Private", system_category=AssetType.Category.OTHER
        )
        response = self.post_json(
            "portfolios:holdings",
            self.holding_payload(asset_type_id=str(private_type.pk)),
            args=[self.portfolio.pk],
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_crud_cannot_target_synced_group_or_holding(self):
        synced_group = Group.objects.create(
            portfolio=self.portfolio,
            name="Broker",
            mode=Group.Mode.SYNCED,
            provider="snaptrade",
            provider_account_id="account-1",
        )
        response = self.post_json(
            "portfolios:holdings",
            self.holding_payload(group_id=str(synced_group.pk)),
            args=[self.portfolio.pk],
        )
        self.assertEqual(response.status_code, 400)

        asset = Asset.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type("Stock"),
            name="AAPL",
        )
        synced = Holding.objects.create(
            group=synced_group,
            asset=asset,
            source=Holding.Source.SYNCED,
            quantity=1,
            provider_security_id="security-1",
        )
        update = self.patch_json(
            "portfolios:holding-detail",
            {"quantity": 2},
            args=[self.portfolio.pk, synced.pk],
        )
        delete = self.delete_json(
            "portfolios:holding-detail", args=[self.portfolio.pk, synced.pk]
        )
        self.assertEqual(update.status_code, 400)
        self.assertEqual(delete.status_code, 400)

    @override_settings(
        ENTITLEMENT_POLICY={"FREE": {"limits": {"holdings": 1}}}
    )
    def test_holding_limit_is_enforced(self):
        first = self.post_json(
            "portfolios:holdings", self.holding_payload(), args=[self.portfolio.pk]
        )
        second = self.post_json(
            "portfolios:holdings", self.holding_payload(), args=[self.portfolio.pk]
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.json()["error"]["code"], "entitlement_limit_reached")

    def test_overview_aggregates_by_group_and_type_without_external_services(self):
        self.post_json(
            "portfolios:holdings", self.holding_payload(), args=[self.portfolio.pk]
        )
        self.post_json(
            "portfolios:holdings",
            {
                "name": "Mystery",
                "asset_type_id": str(asset_type("Other").pk),
            },
            args=[self.portfolio.pk],
        )
        response = self.client.get(
            reverse("portfolios:overview", args=[self.portfolio.pk])
        )
        overview = response.json()["overview"]
        self.assertEqual(overview["total_value"], "90000")
        self.assertEqual(overview["holding_count"], 2)
        self.assertEqual(overview["unknown_value_count"], 1)
        self.assertTrue(any(row["name"] == "Cars" for row in overview["by_group"]))
