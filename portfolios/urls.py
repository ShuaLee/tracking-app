from django.urls import path

from . import views


app_name = "portfolios"

urlpatterns = [
    path("market/search/", views.market_search, name="market-search"),
    path("portfolios/", views.portfolios, name="list"),
    path("portfolios/<uuid:portfolio_id>/", views.portfolio_detail, name="detail"),
    path("portfolios/<uuid:portfolio_id>/groups/", views.groups, name="groups"),
    path(
        "portfolios/<uuid:portfolio_id>/groups/<uuid:group_id>/",
        views.group_detail,
        name="group-detail",
    ),
    path("asset-types/", views.asset_types, name="asset-types"),
    path(
        "asset-types/<uuid:asset_type_id>/",
        views.asset_type_detail,
        name="asset-type-detail",
    ),
    path("portfolios/<uuid:portfolio_id>/holdings/", views.holdings, name="holdings"),
    path(
        "portfolios/<uuid:portfolio_id>/market-holdings/",
        views.market_holdings,
        name="market-holdings",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/holdings/<uuid:holding_id>/",
        views.holding_detail,
        name="holding-detail",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/holdings/<uuid:holding_id>/relink/",
        views.relink_holding,
        name="holding-relink",
    ),
    path("portfolios/<uuid:portfolio_id>/overview/", views.overview, name="overview"),
]
