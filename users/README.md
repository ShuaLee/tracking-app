# Users application

Owns authentication identity and the lightweight user Profile. `models.py` stays intentionally small because User and Profile form one cohesive identity domain. `services.py` handles account lifecycle operations, while `views.py`, `serializers.py`, `forms.py`, and `http.py` define the web/API boundary.

Portfolio, provider, and billing behavior must not be added to the User model.
