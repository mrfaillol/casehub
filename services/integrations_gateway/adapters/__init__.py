"""Provider adapters for the integrations gateway.

v0 ships only a synthetic adapter. Live adapters (real provider SDK / HTTP
calls) are a Council-gated future slice and must not be added here without a
ruling — see ``docs/integrations/casehub-integrations-gateway.md``.
"""
from .base import GatewayAdapter
from .synthetic import SyntheticAdapter

__all__ = ["GatewayAdapter", "SyntheticAdapter"]
