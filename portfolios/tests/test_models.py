from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from portfolios.models import Asset, AssetType, Group, Holding
from portfolios.services.holdings import create_manual_holding, create_portfolio

from .factories import asset_type, user


class PortfolioModelTests(TestCase):
    def setUp(self):
        self.user = user()
        self.portfolio = create_portfolio(owner=self.user, name="Wealth", base_currency="cad")

    def test_portfolio_normalizes_currency_and_has_one_ungrouped_group(self):
        self.assertEqual(self.portfolio.base_currency, "CAD")
        ungrouped = self.portfolio.groups.get(is_ungrouped=True)
        self.assertEqual(ungrouped.name, "Ungrouped")
        self.assertEqual(ungrouped.mode, Group.Mode.SYSTEM)

    def test_database_prevents_second_ungrouped_group(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Group.objects.create(
                portfolio=self.portfolio,
                name="Another",
                mode=Group.Mode.SYSTEM,
                is_ungrouped=True,
            )

    def test_ungrouped_must_be_system(self):
        group = Group(
            portfolio=self.portfolio,
            name="Bad",
            mode=Group.Mode.MANUAL,
            is_ungrouped=True,
        )
        with self.assertRaises(ValidationError):
            group.full_clean()

    def test_synced_group_requires_provider_identity(self):
        group = Group(
            portfolio=self.portfolio, name="Broker", mode=Group.Mode.SYNCED
        )
        with self.assertRaises(ValidationError):
            group.full_clean()

    def test_builtin_asset_types_were_seeded(self):
        names = set(AssetType.objects.filter(owner__isnull=True).values_list("name", flat=True))
        self.assertTrue({"Stock", "Cash", "Home", "Car", "Precious Metal", "Other"} <= names)

    def test_asset_type_cannot_cross_user_boundary(self):
        other = user("other@example.com")
        custom = AssetType.objects.create(
            owner=other,
            name="Watch",
            system_category=AssetType.Category.COLLECTIBLE,
        )
        asset = Asset(
            portfolio=self.portfolio,
            asset_type=custom,
            name="Watch",
        )
        with self.assertRaises(ValidationError):
            asset.full_clean()

    def test_holding_cannot_cross_portfolios(self):
        other_portfolio = create_portfolio(owner=user("other@example.com"), name="Other")
        asset = Asset.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type(),
            name="Asset",
        )
        holding = Holding(
            group=other_portfolio.groups.get(is_ungrouped=True),
            asset=asset,
            quantity=1,
        )
        with self.assertRaises(ValidationError):
            holding.full_clean()

    def test_manual_holding_cannot_contain_provider_state_or_synced_group(self):
        synced = Group.objects.create(
            portfolio=self.portfolio,
            name="Broker",
            mode=Group.Mode.SYNCED,
            provider="snaptrade",
            provider_account_id="account-1",
        )
        asset = Asset.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type(),
            name="Asset",
        )
        holding = Holding(
            group=synced,
            asset=asset,
            source=Holding.Source.MANUAL,
            provider_security_id="provider-security",
        )
        with self.assertRaises(ValidationError):
            holding.full_clean()

    def test_duplicate_holdings_are_permitted(self):
        first = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type(),
            name="Gold",
            quantity=1,
            manual_value=100,
        )
        second = create_manual_holding(
            portfolio=self.portfolio,
            asset_type=asset_type(),
            name="Gold",
            quantity=1,
            manual_value=100,
        )
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(Holding.objects.count(), 2)

    def test_negative_financial_values_are_rejected(self):
        asset = Asset.objects.create(
            portfolio=self.portfolio, asset_type=asset_type(), name="Asset"
        )
        holding = Holding(
            group=self.portfolio.groups.get(is_ungrouped=True),
            asset=asset,
            quantity=Decimal("-1"),
        )
        with self.assertRaises(ValidationError):
            holding.full_clean()
