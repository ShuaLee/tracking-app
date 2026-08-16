# Portfolio API

- `views.py` and `serializers.py` expose portfolio ownership workflows.
- `analytics_views.py` and `analytics_serializers.py` expose themes, income, and configurable Views.

API modules handle authentication, JSON parsing, resource lookup, and response formatting. Business validation and mutations must be delegated to service modules.
