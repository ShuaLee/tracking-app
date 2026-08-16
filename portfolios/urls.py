"""Public URL routes for ownership and analytics APIs."""

from django.urls import path

from .api import analytics_views, views


app_name = "portfolios"

urlpatterns = [
    path("market/search/", views.market_search, name="market-search"),
    path("view-templates/", analytics_views.view_templates, name="view-templates"),
    path("view-schema/", analytics_views.view_schema, name="view-schema"),
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
    path(
        "portfolios/<uuid:portfolio_id>/themes/",
        analytics_views.themes,
        name="themes",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/themes/<uuid:theme_id>/",
        analytics_views.theme_detail,
        name="theme-detail",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/themes/<uuid:theme_id>/holdings/",
        analytics_views.theme_assignments,
        name="theme-assignments",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/themes/<uuid:theme_id>/analytics/",
        analytics_views.theme_analytics,
        name="theme-analytics",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/holdings/<uuid:holding_id>/theme/",
        analytics_views.theme_unassign,
        name="theme-unassign",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/holdings/<uuid:holding_id>/classification/",
        analytics_views.holding_classification,
        name="holding-classification",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/income-rules/",
        analytics_views.income_rules,
        name="income-rules",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/income-rules/<uuid:rule_id>/",
        analytics_views.income_rule_detail,
        name="income-rule-detail",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/income-projections/",
        analytics_views.income_projections,
        name="income-projections",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/views/",
        analytics_views.saved_views,
        name="views",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/views/<uuid:view_id>/",
        analytics_views.saved_view_detail,
        name="view-detail",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/views/<uuid:view_id>/blocks/",
        analytics_views.view_blocks,
        name="view-blocks",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/views/<uuid:view_id>/blocks/<uuid:block_id>/",
        analytics_views.view_block_detail,
        name="view-block-detail",
    ),
    path(
        "portfolios/<uuid:portfolio_id>/views/<uuid:view_id>/render/",
        analytics_views.render_saved_view,
        name="view-render",
    ),
]
