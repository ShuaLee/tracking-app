from subscriptions.models import Subscription
from users.models import User

from portfolios.models import AssetType
from portfolios.services import create_portfolio


PASSWORD = "A-strong-password-927!"


def user(email="person@example.com", *, plan=Subscription.Plan.FREE):
    instance = User.objects.create_user(email, PASSWORD)
    instance.subscription.plan = plan
    instance.subscription.save()
    return instance


def portfolio(owner, name="My Portfolio", currency="USD"):
    return create_portfolio(owner=owner, name=name, base_currency=currency)


def asset_type(name="Other"):
    return AssetType.objects.get(owner__isnull=True, name=name)

