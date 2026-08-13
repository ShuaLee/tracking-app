def subscription_data(subscription):
    return {
        "plan": subscription.plan,
        "status": subscription.status,
    }


def user_data(user):
    return {
        "id": str(user.id),
        "email": user.email,
        "profile": {"name": user.profile.name},
        "subscription": subscription_data(user.subscription),
    }

