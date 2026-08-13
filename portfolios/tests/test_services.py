from decimal import Decimal

from django.test import TestCase, override_settings

from portfolios.exceptions import EntitlementLimitError, PortfolioDomainError, ProtectedOperationError
from portfolios.models import Asset, AssetType, Group, Holding, Portfolio
from portfolios.services import (
    create_custom_asset_type,
    create_manual_group,
    create_manual_holding,
    create_portfolio,
    delete_custom_asset_type,
    delete_manual_group,
    delete_manual_holding,
    delete_portfolio,
    portfolio_overview,
    update_manual_holding,
)

from .factories import asset_type, user


class PortfolioServiceTests(TestCase):
    def setUp(self):
        self.user = user()
        self.portfolio = create_portfolio(owner=self.user, name="My Portfolio")

    def test_free_portfolio_limit_is_enforced(self):
        with self.assertRaises(EntitlementLimitError):
            create_portfolio(owner=self.user, name="Second")

    @override_settings(
        ENTITLEMENT_POLICY={"FREE": {"limits": {"portfolios": 2, "holdings": 1}}}
    )
    def test_configurable_limits_are_enforced_across_user_portfolios(self):
        second = create_portfolio(owner=self.user, name="Second")
        create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type(),
            name="One",
        )
        with self.assertRaises(EntitlementLimitError):
            create_manual_holding(
                portfolio=second,
                asset_type=asset_type(),
                name="Two",
            )

    def test_manual_holding_defaults_to_ungrouped(self):
        holding = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type("Home"),
            name="123 Main Street",
            native_currency="cad",
            quantity="1",
            average_cost="500000",
            cost_currency="cad",
            manual_value="750000",
            metadata={"city": "Toronto"},
        )
        self.assertTrue(holding.group.is_ungrouped)
        self.assertEqual(holding.asset.native_currency, "CAD")
        self.assertEqual(holding.manual_value, Decimal("750000"))

    def test_manual_group_delete_moves_holdings_to_ungrouped(self):
        group = create_manual_group(portfolio=self.portfolio, name="Cars")
        holding = create_manual_holding(
            portfolio=self.portfolio,
            group=group,
            asset_type=asset_type("Car"),
            name="Porsche",
        )

        delete_manual_group(group=group)

        holding.refresh_from_db()
        self.assertTrue(holding.group.is_ungrouped)
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())

    def test_system_and_synced_groups_are_protected(self):
        with self.assertRaises(ProtectedOperationError):
            delete_manual_group(group=self.portfolio.groups.get(is_ungrouped=True))
        synced = Group.objects.create(
            portfolio=self.portfolio,
            name="Broker",
            mode=Group.Mode.SYNCED,
            provider="snaptrade",
            provider_account_id="account-1",
        )
        with self.assertRaises(ProtectedOperationError):
            delete_manual_group(group=synced)

    def test_manual_holding_can_move_but_not_into_synced_group(self):
        cars = create_manual_group(portfolio=self.portfolio, name="Cars")
        holding = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type("Car"),
            name="Car",
        )
        update_manual_holding(holding=holding, group=cars)
        self.assertEqual(holding.group, cars)

        synced = Group.objects.create(
            portfolio=self.portfolio,
            name="Broker",
            mode=Group.Mode.SYNCED,
            provider="snaptrade",
            provider_account_id="account-1",
        )
        with self.assertRaises(ProtectedOperationError):
            update_manual_holding(holding=holding, group=synced)

    def test_cross_portfolio_group_is_rejected(self):
        other_user = user("other@example.com")
        other_portfolio = create_portfolio(owner=other_user, name="Other")
        with self.assertRaises(PortfolioDomainError):
            create_manual_holding(
                portfolio=self.portfolio,
                group=other_portfolio.groups.get(is_ungrouped=True),
                asset_type=asset_type(),
                name="Bad",
            )

    def test_custom_asset_type_is_protected_while_in_use(self):
        custom = create_custom_asset_type(
            owner=self.user,
            name="Pokemon Card",
            system_category=AssetType.Category.COLLECTIBLE,
        )
        create_manual_holding(
            portfolio=self.portfolio,
            asset_type=custom,
            name="Charizard",
        )
        with self.assertRaises(ProtectedOperationError):
            delete_custom_asset_type(asset_type=custom)

    def test_deleting_holding_removes_orphan_asset(self):
        holding = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type(),
            name="Asset",
        )
        asset_id = holding.asset_id
        delete_manual_holding(holding=holding)
        self.assertFalse(Asset.objects.filter(pk=asset_id).exists())

    def test_portfolio_delete_removes_protected_ownership_graph_safely(self):
        create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type(),
            name="Asset",
        )
        delete_portfolio(portfolio=self.portfolio)
        self.assertFalse(Portfolio.objects.filter(pk=self.portfolio.pk).exists())
        self.assertFalse(Holding.objects.exists())

    def test_overview_aggregates_known_values_and_reports_unknowns(self):
        cars = create_manual_group(portfolio=self.portfolio, name="Cars")
        create_manual_holding(
            portfolio=self.portfolio,
            group=cars,
            asset_type=asset_type("Car"),
            name="Car",
            manual_value="90000",
        )
        create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type("Other"),
            name="Unknown",
        )
        overview = portfolio_overview(self.portfolio)
        self.assertEqual(overview["total_value"], Decimal("90000"))
        self.assertEqual(overview["holding_count"], 2)
        self.assertEqual(overview["unknown_value_count"], 1)

