from django.db.models.signals import post_save
from django.dispatch import receiver

from subscriptions.models import Subscription

from .models import Profile, User


@receiver(post_save, sender=User, dispatch_uid="users.create_account_dependencies")
def create_account_dependencies(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        Subscription.objects.create(user=instance)

