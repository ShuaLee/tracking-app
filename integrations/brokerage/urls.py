from django.urls import path

from . import views


app_name = "brokerage"

urlpatterns = [
    path("brokerage/portal/", views.portal, name="portal"),
    path("brokerage/connections/", views.connections, name="connections"),
    path("brokerage/connections/<uuid:connection_id>/sync/", views.sync, name="sync"),
    path("brokerage/connections/<uuid:connection_id>/refresh/", views.refresh, name="refresh"),
    path("brokerage/connections/<uuid:connection_id>/", views.disconnect, name="disconnect"),
]
