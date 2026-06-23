"""External-call hard timeouts (incident 2026-06-16 VS 504 mitigation 2/N).

A slow external upstream must not be able to pin a uvicorn worker for minutes.
These assert the timeout knobs exist, are bounded under the nginx ceiling, and
are env-tunable. Imports stay light (config + maestro_lite only) so this runs
without the full app/route import chain.
"""
import os
import importlib


def test_config_external_timeouts_bounded_and_ordered():
    from config import settings
    http_t = float(settings.EXTERNAL_HTTP_TIMEOUT_S)
    llm_t = float(settings.EXTERNAL_LLM_TIMEOUT_S)
    assert http_t > 0 and llm_t > 0
    # general http timeout is the tighter bound; LLM is allowed to be longer
    assert http_t <= llm_t
    # both must stay under the most generous nginx proxy_read_timeout (300s),
    # so a call cannot outlive nginx and keep grinding after the client gave up
    assert http_t < 300 and llm_t < 300


def test_maestro_lite_llm_timeout_bounded():
    import services.maestro_lite as m
    assert hasattr(m, "LLM_TIMEOUT_S")
    assert 0 < float(m.LLM_TIMEOUT_S) < 300


def test_maestro_lite_llm_timeout_is_env_tunable():
    prev = os.environ.get("EXTERNAL_LLM_TIMEOUT_S")
    os.environ["EXTERNAL_LLM_TIMEOUT_S"] = "30"
    try:
        import services.maestro_lite as m
        importlib.reload(m)
        assert float(m.LLM_TIMEOUT_S) == 30.0
    finally:
        if prev is None:
            os.environ.pop("EXTERNAL_LLM_TIMEOUT_S", None)
        else:
            os.environ["EXTERNAL_LLM_TIMEOUT_S"] = prev
        import services.maestro_lite as m
        importlib.reload(m)
