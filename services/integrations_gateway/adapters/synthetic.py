from __future__ import annotations

import copy

from ..types import GatewayRequest, GatewayResult

# Canned, already-sanitized fixtures. No network, no DB, no real provider data.
# Keyed by provider name then operation; mirrors registry.DEFAULT_PROVIDER_CONFIGS.
_FIXTURES: dict[str, dict[str, dict]] = {
    "google-calendar": {
        "status.read": {"account": "synthetic", "calendars": 1, "writable": True},
        "events.read": {"events": [{"id": "synthetic-evt-1", "title": "Fixture event"}]},
        "events.create": {"event_id": "synthetic-evt-created"},
        "events.update": {"event_id": "synthetic-evt-1", "updated": True},
        "events.delete": {"event_id": "synthetic-evt-1", "deleted": True},
    },
    "gmail": {
        "threads.search": {"threads": [{"id": "synthetic-thread-1", "snippet": "fixture"}]},
        "threads.read": {"thread_id": "synthetic-thread-1", "messages": 1},
    },
    "google-drive": {
        "files.search": {"files": [{"id": "synthetic-file-1", "name": "fixture.pdf"}]},
        "files.read": {"file_id": "synthetic-file-1", "size": 0},
        "evidence.export": {"export_id": "synthetic-export-1"},
    },
}


class SyntheticAdapter:
    """Test-bench adapter. Returns canned fixtures and performs zero I/O.

    Satisfies the :class:`GatewayAdapter` protocol. This is the only adapter
    shipped in gateway v0; it lets the policy / credential / audit path be
    exercised before any live provider call exists.
    """

    synthetic = True

    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def execute(self, request: GatewayRequest) -> GatewayResult:
        operations = _FIXTURES.get(self.provider_name, {})
        if request.operation not in operations:
            return GatewayResult(
                ok=False,
                provider_name=self.provider_name,
                operation=request.operation,
                synthetic=True,
                error="no_synthetic_fixture",
            )
        return GatewayResult(
            ok=True,
            provider_name=self.provider_name,
            operation=request.operation,
            synthetic=True,
            data=copy.deepcopy(operations[request.operation]),
        )
