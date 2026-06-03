import re
from pathlib import Path

import pytest


DEPLOY_CONFIGS = [
    Path("deploy/nginx-casehub.conf"),
    Path("deploy/nginx-demo.conf"),
]


def _location_block(config: str, location: str) -> str:
    match = re.search(rf"location {re.escape(location)} \{{(?P<block>.*?)\n    \}}", config, re.S)
    assert match, f"missing nginx location {location}"
    return match.group("block")


@pytest.mark.parametrize("config_path", DEPLOY_CONFIGS)
def test_nginx_serves_casehub_prefixed_static_assets(config_path):
    config = config_path.read_text()
    block = _location_block(config, "/casehub/static/")

    assert "alias /opt/casehub/static/;" in block
    assert "try_files $uri =404;" in block
    assert 'set $casehub_static_cache_control "public, max-age=3600";' in block
    assert 'set $casehub_static_cache_control "public, max-age=31536000, immutable";' in block
    assert "gzip_static on;" in block
    assert "gzip_types text/css application/javascript application/json image/svg+xml;" in block
    assert "proxy_pass" not in block


@pytest.mark.parametrize("config_path", DEPLOY_CONFIGS)
def test_nginx_keeps_legacy_static_alias_without_uvicorn_proxy(config_path):
    config = config_path.read_text()
    block = _location_block(config, "/static/")

    assert "alias /opt/casehub/static/;" in block
    assert "proxy_pass" not in block
