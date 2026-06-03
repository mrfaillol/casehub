from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..types import GatewayRequest, GatewayResult


@runtime_checkable
class GatewayAdapter(Protocol):
    """Contract every provider adapter satisfies.

    `synthetic` must be ``True`` for any adapter that does not perform live
    provider I/O. A live adapter (future, Council-gated) would set it ``False``.
    """

    provider_name: str
    synthetic: bool

    def execute(self, request: GatewayRequest) -> GatewayResult:
        ...
