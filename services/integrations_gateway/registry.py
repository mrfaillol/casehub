from .types import GatewayProviderConfig


DEFAULT_PROVIDER_CONFIGS = (
    GatewayProviderConfig(
        name="google-calendar",
        allowed_operations=(
            "status.read",
            "events.read",
            "events.create",
            "events.update",
            "events.delete",
        ),
        mutating_operations=(
            "events.create",
            "events.update",
            "events.delete",
        ),
    ),
    GatewayProviderConfig(
        name="gmail",
        allowed_operations=(
            "threads.search",
            "threads.read",
        ),
        mutating_operations=(),
    ),
    GatewayProviderConfig(
        name="google-drive",
        allowed_operations=(
            "files.search",
            "files.read",
            "evidence.export",
        ),
        mutating_operations=("evidence.export",),
    ),
)


def get_default_provider_configs() -> tuple[GatewayProviderConfig, ...]:
    return DEFAULT_PROVIDER_CONFIGS
