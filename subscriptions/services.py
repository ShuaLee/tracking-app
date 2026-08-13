from django.db import transaction

from .models import Subscription


@transaction.atomic
def change_subscription(*, subscription, plan=None, status=None):
    if plan is not None:
        subscription.plan = plan
    if status is not None:
        subscription.status = status
    subscription.full_clean()
    subscription.save()
    return subscription

