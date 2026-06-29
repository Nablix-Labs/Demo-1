"""Adapter package for every external-service boundary.

Routes and services should not import concrete downstream clients directly.
They receive protocol-shaped adapters from `provider.get_adapters()` and work
with typed DTOs from `app.models.adapters`. Concrete adapters own the choice
between deterministic mock data and real service calls.
"""
