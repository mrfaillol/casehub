from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_whatsapp_chat_template_has_disconnect_banner():
    html = read_repo_file("templates/app/whatsapp/chat.html")

    assert 'id="waDisconnectBar"' in html
    assert 'id="waDisconnectReason"' in html
    assert 'onclick="forceReconnect()"' in html
    assert 'id="waConnectStateText"' in html
    assert 'id="waConnectMode" role="tablist"' in html
    assert 'id="waConnectMode" role="tablist" aria-label="Modo de conexão WhatsApp" hidden' not in html


def test_fastapi_reconnect_proxy_preserves_session():
    source = read_repo_file("routes/whatsapp_chat.py")

    assert 'f"{WHATSAPP_BOT_URL}/api/reconnect"' in source
    assert "Failed to reconnect" in source
    assert 'f"{WHATSAPP_BOT_URL}/api/disconnect", timeout=30.0' not in source


def test_qr_self_heal_never_wipes_saved_session():
    source = read_repo_file("routes/whatsapp_chat.py")
    start = source.index("@router.get(\"/api/qr\")")
    end = source.index("@router.post(\"/api/pairing-code\")", start)
    body = source[start:end]

    assert "status in _QR_STALE_STATUSES" in body
    assert 'f"{WHATSAPP_BOT_URL}/api/reconnect"' in body
    assert "/api/disconnect" not in body
    assert "clearAndReinitialize" not in body
    assert "{ confirm: 'wipe' }" not in body


def test_bot_exposes_soft_reconnect_and_non_pairing_health():
    source = read_repo_file("services/whatsapp-bot/server-lite.js")

    assert 'app.post("/api/reconnect"' in source
    assert "await client.softReconnect()" in source
    assert "client.getStatusVerified" in source
    assert "whatsappReady" in source
    assert "requiresPairing" in source
    assert "res.status(200).json" in source


def test_local_auth_session_backup_restore_and_prewipe_contract():
    client_source = read_repo_file("services/whatsapp-bot/whatsapp-client.js")
    server_source = read_repo_file("services/whatsapp-bot/server-lite.js")

    init_start = client_source.index("async initialize")
    local_auth_idx = client_source.index("authStrategy: new LocalAuth", init_start)
    restore_idx = client_source.index("this._restoreFromBackupOnBoot()", init_start)
    assert restore_idx < local_auth_idx

    assert "backupSession() { return this._snapshotSession(\"__lastgood\"); }" in client_source
    assert "client.backupSession()" in server_source

    clear_start = client_source.index("async clearAndReinitialize")
    clear_end = client_source.index("if (phoneNumber)", clear_start)
    clear_body = client_source[clear_start:clear_end]
    snapshot_idx = clear_body.index("this._snapshotSession(\"__prewipe\")")
    rm_idx = clear_body.index("fs.rmSync(sessionPath")
    assert snapshot_idx < rm_idx
    # clearAndReinitialize must resolve the wipe path via the centralized
    # _sessionDir() helper, not inline the per-org literal (which now lives in
    # _sessionDir() itself). Checking the relationship instead of a moved literal
    # keeps this contract honest without masking a regression.
    assert "this._sessionDir()" in clear_body, (
        "clearAndReinitialize() must resolve the wipe path via this._sessionDir()"
    )
    session_dir_start = client_source.index("_sessionDir() {")
    session_dir_end = client_source.index("_sessionLooksPresent", session_dir_start)
    session_dir_body = client_source[session_dir_start:session_dir_end]
    assert "`session-org-${this.orgId}`" in session_dir_body, (
        "_sessionDir() must build the per-org 'session-org-<id>' path"
    )


def test_alpha_compose_persists_whatsapp_auth_and_media_volumes():
    source = read_repo_file("docker-compose.alpha.yml")

    assert "whatsapp_session:/app/.wwebjs_auth" in source
    assert "whatsapp_session:" in source
    assert "whatsapp_media:/app/media" in source
    assert "name: casehub_whatsapp_media" in source
    assert "CASEHUB_DEFAULT_ORG_ID" in source
    assert "CASEHUB_AUTOSTART_ORGS" in source


def test_alpha_deploy_seeds_whatsapp_media_volume_before_recreate():
    source = read_repo_file(".github/workflows/deploy-alpha.yml")

    build_idx = source.index("compose build casehub whatsapp-bot")
    seed_idx = source.index("seed_whatsapp_media_volume", build_idx)
    recreate_idx = source.index("compose up -d --force-recreate", seed_idx)

    assert build_idx < seed_idx < recreate_idx
    assert "docker cp casehub-whatsapp-bot:/app/media/." in source
    assert "docker volume create casehub_whatsapp_media" in source
    assert "-v casehub_whatsapp_media:/app/media" in source
    assert "cp -an /media-seed/. /app/media/" in source


def test_alpha_deploy_rollback_does_not_run_when_hotfix_guard_blocks():
    source = read_repo_file(".github/workflows/deploy-alpha.yml")

    rollback_idx = source.index("- name: Roll back to previous healthy SHA")
    rollback_body = source[rollback_idx:source.index("      - name:", rollback_idx + 1)]

    assert "steps.hotfix_guard.outcome == 'success'" in rollback_body
    assert "guard that fail-closed to protect a live" in rollback_body


def test_reconnect_button_calls_backend_endpoint():
    source = read_repo_file("static/js/chat.js")

    assert "fetchAPI('/api/reconnect'" in source
    assert "window.setConnectStateText = setConnectStateText" in source
    assert "btn.disabled = true" in source
    assert "btn.disabled = false" in source


def test_chat_js_uses_template_injected_api_base():
    source = read_repo_file("static/js/chat.js")
    assignment = source[source.index("const WHATSAPP_API_BASE"):source.index("async function fetchAPI")]

    assert "window.WA_API_BASE" in assignment
    assert "WA_API_BASE" in assignment
    assert "/whatsapp-chat" in assignment  # legacy fallback only


def test_fastapi_messages_endpoint_prefers_persisted_history_before_bot_fallback():
    source = read_repo_file("routes/whatsapp_chat.py")
    start = source.index("@router.get(\"/api/messages/{phone}\")")
    end = source.index("def _normalize_phone_digits", start)
    body = source[start:end]

    db_idx = body.index("whatsapp_clone_service.list_messages")
    bot_idx = body.index("get_bot_messages")
    assert db_idx < bot_idx


def test_history_backfill_is_explicit_and_preserves_read_state():
    route_source = read_repo_file("routes/whatsapp_chat.py")
    service_source = read_repo_file("services/whatsapp_clone_service.py")
    js_source = read_repo_file("static/js/chat.js")
    html_source = read_repo_file("templates/app/whatsapp/chat.html")

    assert '@router.post("/api/history/backfill/{phone}")' in route_source
    assert "get_bot_messages(phone, limit, request=request)" in route_source
    assert "increment_unread=False" in route_source
    assert "increment_unread: bool = True" in service_source
    assert "if not from_me and increment_unread:" in service_source
    assert "backfillHistory()" in html_source
    assert "fetchAPI(`/api/history/backfill/${encodeURIComponent(phone)}`" in js_source


def test_frontend_click_loads_and_renders_messages_chronologically():
    source = read_repo_file("static/js/chat.js")

    assert "onclick=\"selectConversation('${c.phone}')\"" in source
    assert "await loadMessages(phone, loadId)" in source
    assert "fetchAPI(`/api/messages/${phone}`)" in source
    assert "renderWhatsAppMessages = function()" in source
    assert ".sort((a, b) => (getMessageTs(a.m) - getMessageTs(b.m))" in source
