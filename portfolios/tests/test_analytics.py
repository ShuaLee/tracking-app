"""Domain tests for income, themes, and configurable portfolio views."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from integrations.market_data.contracts import DividendEvent
from portfolios.exceptions import PortfolioDomainError, ProtectedOperationError
from portfolios.analytics.income import projections_for_holding
from portfolios.models import IncomeRule, Theme, ThemeAssignment, ViewBlock
from portfolios.analytics.services import (
    assign_theme,
    create_block,
    create_income_rule,
    create_theme,
    create_view,
    create_view_from_template,
    delete_theme,
    delete_view,
    update_block,
    update_theme,
)
from portfolios.tests.factories import asset_type, portfolio, user
from portfolios.services.holdings import create_manual_holding, delete_portfolio
from portfolios.analytics.engine import ViewAnalyticsContext, render_block, render_view
from subscriptions.models import Subscription


class Stage5DomainTests(TestCase):
    def setUp(self):
        self.owner = user(plan=Subscription.Plan.PRO)
        self.portfolio = portfolio(self.owner)
        self.holding = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type("Other"),
            name="Rental",
            native_currency="USD",
            country_code="US",
            sector="Real Estate",
            industry="Residential Property",
            quantity="1",
            average_cost="500",
            cost_currency="USD",
            manual_value="1000",
        )

    def test_analytics_objects_are_optional_and_no_view_is_created_implicitly(self):
        self.assertFalse(self.portfolio.themes.exists())
        self.assertFalse(self.portfolio.saved_views.exists())
        self.assertFalse(IncomeRule.objects.exists())

    def test_free_plan_cannot_create_advanced_analytics_data(self):
        free_owner = user("free-analytics@example.com")
        free_portfolio = portfolio(free_owner)

        with self.assertRaises(PortfolioDomainError) as raised:
            create_view(portfolio=free_portfolio, name="Private view")

        self.assertEqual(raised.exception.code, "entitlement_required")

    def test_theme_hierarchy_assignment_and_cycle_protection(self):
        parent = create_theme(
            portfolio=self.portfolio, name="Technology", target_percentage="30"
        )
        child = create_theme(portfolio=self.portfolio, name="AI", parent=parent)
        assignment = assign_theme(theme=child, holding=self.holding)

        self.assertEqual(assignment.theme, child)
        self.assertEqual(ThemeAssignment.objects.count(), 1)
        with self.assertRaises(ProtectedOperationError):
            delete_theme(parent)

        with self.assertRaises(PortfolioDomainError):
            update_theme(parent, parent=child)

    def test_portfolio_deletion_removes_an_entire_theme_tree(self):
        parent = create_theme(portfolio=self.portfolio, name="Parent")
        create_theme(portfolio=self.portfolio, name="Child", parent=parent)

        delete_portfolio(portfolio=self.portfolio)

        self.assertFalse(Theme.objects.exists())

    def test_assigning_again_moves_holding_instead_of_double_counting(self):
        first = create_theme(portfolio=self.portfolio, name="First")
        second = create_theme(portfolio=self.portfolio, name="Second")

        assign_theme(theme=first, holding=self.holding)
        assign_theme(theme=second, holding=self.holding)

        self.assertEqual(ThemeAssignment.objects.count(), 1)
        self.assertEqual(self.holding.theme_assignment.theme, second)

    def test_income_rule_annualizes_standard_and_custom_frequency(self):
        monthly = create_income_rule(
            holding=self.holding,
            name="Rent",
            category=IncomeRule.Category.RENT,
            amount_per_payment="100",
            currency="usd",
            frequency=IncomeRule.Frequency.MONTHLY,
        )
        custom = create_income_rule(
            holding=self.holding,
            name="Royalty",
            category=IncomeRule.Category.ROYALTY,
            amount_per_payment="25",
            currency="USD",
            frequency=IncomeRule.Frequency.CUSTOM,
            payments_per_year="6",
        )

        self.assertEqual(monthly.annual_amount, Decimal("1200"))
        self.assertEqual(custom.annual_amount, Decimal("150"))
        self.assertEqual(monthly.currency, "USD")

    def test_custom_income_frequency_requires_multiplier(self):
        with self.assertRaises(PortfolioDomainError):
            create_income_rule(
                holding=self.holding,
                name="Invalid",
                category=IncomeRule.Category.OTHER,
                amount_per_payment="10",
                currency="USD",
                frequency=IncomeRule.Frequency.CUSTOM,
            )

    def test_market_dividends_are_trailing_twelve_month_projection(self):
        asset = self.holding.asset
        asset.market_linked = True
        asset.market_data_status = asset.MarketDataStatus.LINKED
        asset.market_symbol = "TEST"
        asset.market_exchange = "NYSE"
        asset.market_identity = {"symbol": "TEST", "exchange": "NYSE"}
        asset.save()
        market = Mock()
        market.get_dividends.return_value = [
            DividendEvent(
                symbol="TEST",
                ex_date=timezone.localdate() - timedelta(days=30),
                amount=Decimal("2"),
                currency="USD",
            ),
            DividendEvent(
                symbol="TEST",
                ex_date=timezone.localdate() - timedelta(days=400),
                amount=Decimal("99"),
                currency="USD",
            ),
        ]

        projections = projections_for_holding(self.holding, market_service=market)

        market_projection = next(item for item in projections if item.source == "MARKET")
        self.assertEqual(market_projection.annual_amount, Decimal("2"))

    def test_view_templates_are_copied_configuration_not_permanent_data(self):
        blank = create_view_from_template(
            portfolio=self.portfolio, name="Blank", template=None
        )
        themed = create_view_from_template(
            portfolio=self.portfolio, name="Optional Theme View", template="themes"
        )

        self.assertFalse(blank.blocks.exists())
        self.assertEqual(themed.blocks.count(), 2)
        self.assertFalse(self.portfolio.themes.exists())
        self.assertFalse(IncomeRule.objects.exists())

    def test_deleting_view_never_deletes_financial_or_classification_data(self):
        theme = create_theme(portfolio=self.portfolio, name="Property")
        assign_theme(theme=theme, holding=self.holding)
        rule = create_income_rule(
            holding=self.holding,
            name="Rent",
            category=IncomeRule.Category.RENT,
            amount_per_payment="100",
            currency="USD",
            frequency=IncomeRule.Frequency.MONTHLY,
        )
        view = create_view_from_template(
            portfolio=self.portfolio, name="Disposable", template="income"
        )

        delete_view(view)

        self.assertTrue(self.portfolio.groups.filter(holdings=self.holding).exists())
        self.assertTrue(Theme.objects.filter(pk=theme.pk).exists())
        self.assertTrue(IncomeRule.objects.filter(pk=rule.pk).exists())

    def test_block_configuration_rejects_unknown_fields_and_formulas(self):
        view = create_view(portfolio=self.portfolio, name="Safe")

        with self.assertRaises(PortfolioDomainError):
            create_block(
                view=view,
                data_source=ViewBlock.DataSource.HOLDINGS,
                presentation=ViewBlock.Presentation.TABLE,
                configuration={"fields": ["asset_name", "raw_sql"]},
            )
        with self.assertRaises(PortfolioDomainError):
            create_block(
                view=view,
                data_source=ViewBlock.DataSource.HOLDINGS,
                presentation=ViewBlock.Presentation.TABLE,
                configuration={"formula": "DROP TABLE holdings"},
            )

    def test_blocks_can_be_inserted_and_reordered(self):
        view = create_view(portfolio=self.portfolio, name="Layout")
        first = create_block(
            view=view,
            title="First",
            data_source="HOLDINGS",
            presentation="TABLE",
        )
        second = create_block(
            view=view,
            title="Second",
            data_source="HOLDINGS",
            presentation="LIST",
        )

        update_block(second, position=0)

        self.assertEqual(
            list(view.blocks.values_list("title", "position")),
            [("Second", 0), ("First", 1)],
        )

    def test_view_engine_filters_groups_sums_and_calculates_yield(self):
        theme = create_theme(portfolio=self.portfolio, name="Property")
        assign_theme(theme=theme, holding=self.holding)
        create_income_rule(
            holding=self.holding,
            name="Rent",
            category=IncomeRule.Category.RENT,
            amount_per_payment="100",
            currency="USD",
            frequency=IncomeRule.Frequency.MONTHLY,
        )
        view = create_view(portfolio=self.portfolio, name="Yield")
        block = create_block(
            view=view,
            data_source="HOLDINGS",
            presentation="TABLE",
            configuration={
                "group_by": "theme",
                "aggregations": [
                    {"field": "value", "function": "sum"},
                    {"field": "annual_income", "function": "sum"},
                ],
                "filters": [
                    {"field": "annual_income", "operator": "greater_than", "value": "0"}
                ],
            },
        )

        result = render_block(block, context=ViewAnalyticsContext(self.portfolio))
        holding_row = ViewAnalyticsContext(self.portfolio).rows("HOLDINGS")[0]

        self.assertEqual(result["rows"][0]["theme"], "Property")
        self.assertEqual(result["rows"][0]["sum_value"], Decimal("1000"))
        self.assertEqual(result["rows"][0]["sum_annual_income"], Decimal("1200"))
        self.assertEqual(holding_row["current_yield"], Decimal("120"))

    def test_custom_cash_flow_summary_can_group_and_sum_monthly_income(self):
        create_income_rule(
            holding=self.holding,
            name="Rent",
            category=IncomeRule.Category.RENT,
            amount_per_payment="100",
            currency="USD",
            frequency=IncomeRule.Frequency.MONTHLY,
        )
        view = create_view(portfolio=self.portfolio, name="My Own Cash Flow")
        block = create_block(
            view=view,
            data_source="INCOME",
            presentation="SUMMARY",
            configuration={
                "group_by": ["currency", "income_type"],
                "aggregations": [
                    {"field": "monthly_income", "function": "sum"}
                ],
            },
        )

        result = render_block(block)

        self.assertEqual(result["rows"], [{
            "currency": "USD",
            "income_type": "RENT",
            "sum_monthly_income": Decimal("100"),
        }])

    def test_income_money_summary_cannot_mix_currencies(self):
        view = create_view(portfolio=self.portfolio, name="Unsafe Currency Total")

        with self.assertRaises(PortfolioDomainError):
            create_block(
                view=view,
                data_source="INCOME",
                presentation="SUMMARY",
                configuration={
                    "aggregations": [
                        {"field": "annual_income", "function": "sum"}
                    ],
                    "group_by": "income_type",
                },
            )

    def test_group_data_source_is_available_without_creating_themes(self):
        rows = ViewAnalyticsContext(self.portfolio).rows("GROUPS")

        self.assertEqual(rows[0]["group"], "Ungrouped")
        self.assertEqual(rows[0]["value"], Decimal("1000"))
        self.assertFalse(self.portfolio.themes.exists())

    def test_theme_analytics_rolls_child_values_into_parent(self):
        parent = create_theme(portfolio=self.portfolio, name="Real Assets")
        child = create_theme(portfolio=self.portfolio, name="Property", parent=parent)
        assign_theme(theme=child, holding=self.holding)

        rows = ViewAnalyticsContext(self.portfolio).rows("THEMES")
        indexed = {row["theme"]: row for row in rows}

        self.assertEqual(indexed["Property"]["value"], Decimal("1000"))
        self.assertEqual(indexed["Real Assets"]["value"], Decimal("1000"))
        self.assertEqual(indexed["Real Assets"]["holding_count"], Decimal("1"))

    def test_selected_scope_drives_country_theme_and_group_analytics(self):
        second = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type("Other"),
            name="Canadian Asset",
            native_currency="USD",
            country_code="CA",
            manual_value="500",
        )
        theme = create_theme(portfolio=self.portfolio, name="Property")
        assign_theme(theme=theme, holding=self.holding)
        assign_theme(theme=theme, holding=second)
        view = create_view_from_template(
            portfolio=self.portfolio,
            name="US Property Only",
            template="country",
            scope_mode="SELECTED",
            holding_ids=[str(self.holding.pk)],
        )

        country_result = render_view(view)[0]
        holding_rows = ViewAnalyticsContext(
            self.portfolio, holding_ids=[self.holding.pk]
        ).rows("HOLDINGS")
        theme_rows = ViewAnalyticsContext(
            self.portfolio, holding_ids=[self.holding.pk]
        ).rows("THEMES")
        group_rows = ViewAnalyticsContext(
            self.portfolio, holding_ids=[self.holding.pk]
        ).rows("GROUPS")

        self.assertEqual(country_result["rows"], [{
            "country": "US",
            "sum_value": Decimal("1000"),
            "sum_annual_income": Decimal("0"),
            "count_holding_id": Decimal("1"),
        }])
        self.assertEqual([row["asset_name"] for row in holding_rows], ["Rental"])
        self.assertEqual(theme_rows[0]["value"], Decimal("1000"))
        self.assertEqual(group_rows[0]["value"], Decimal("1000"))

    def test_view_can_be_cloned_and_then_changed_independently(self):
        source = create_view_from_template(
            portfolio=self.portfolio,
            name="Source Yield",
            template="yield",
            scope_mode="SELECTED",
            holding_ids=[self.holding.pk],
        )

        clone = create_view_from_template(
            portfolio=self.portfolio,
            name="Custom Yield Copy",
            source_view=source,
        )
        update_block(clone.blocks.first(), title="Changed copy")

        self.assertEqual(clone.scope_mode, "SELECTED")
        self.assertEqual(
            list(clone.holding_selections.values_list("holding_id", flat=True)),
            [self.holding.pk],
        )
        self.assertEqual(clone.blocks.count(), source.blocks.count())
        self.assertNotEqual(clone.blocks.first().title, source.blocks.first().title)

        all_assets_clone = create_view_from_template(
            portfolio=self.portfolio,
            name="All Assets Copy",
            source_view=source,
            scope_mode="ALL",
        )
        self.assertEqual(all_assets_clone.scope_mode, "ALL")
        self.assertFalse(all_assets_clone.holding_selections.exists())

    def test_selected_scope_rejects_holdings_from_another_portfolio(self):
        other = user("scope-other@example.com", plan=Subscription.Plan.PRO)
        other_holding = create_manual_holding(
            portfolio=portfolio(other),
            asset_type=asset_type("Other"),
            name="Other",
            manual_value="1",
        )

        with self.assertRaises(PortfolioDomainError):
            create_view(
                portfolio=self.portfolio,
                name="Invalid scope",
                scope_mode="SELECTED",
                holding_ids=[other_holding.pk],
            )
