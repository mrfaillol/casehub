from models.notification import Notification
from models.user import User
from routes.whatsapp_inbound import _is_noisy_health_monitor_reason, _notify_org_disconnect


def _add_staff(db, user_id: int, org_id: int = 4):
    db.add(
        User(
            id=user_id,
            org_id=org_id,
            email=f"staff{user_id}@example.test",
            name=f"Staff {user_id}",
            password_hash="x",
            user_type="admin",
            enabled=True,
        )
    )


def test_noisy_health_monitor_reason_is_not_user_facing(db):
    for reason in (
        "health-monitor:UNKNOWN",
        "health-monitor:UNREACHABLE",
        "health-monitor:TIMEOUT",
        "health-monitor:OPENING",
        "health-monitor:CONNECTING",
    ):
        assert _is_noisy_health_monitor_reason(reason)

    assert not _is_noisy_health_monitor_reason("health-monitor:UNPAIRED")
    assert not _is_noisy_health_monitor_reason("LOGOUT")


def test_health_monitor_unknown_does_not_create_disconnect_notifications(db):
    _add_staff(db, 1)
    _add_staff(db, 2)
    db.commit()

    created = _notify_org_disconnect(db, 4, "health-monitor:UNKNOWN")

    assert created == 0
    assert db.query(Notification).count() == 0


def test_fatal_disconnect_still_notifies_enabled_staff(db):
    _add_staff(db, 1)
    _add_staff(db, 2)
    db.add(
        User(
            id=3,
            org_id=4,
            email="disabled@example.test",
            name="Disabled",
            password_hash="x",
            user_type="admin",
            enabled=False,
        )
    )
    db.commit()

    created = _notify_org_disconnect(db, 4, "LOGOUT")

    assert created == 2
    notifications = db.query(Notification).order_by(Notification.user_id).all()
    assert [n.user_id for n in notifications] == [1, 2]
    assert {n.notification_type for n in notifications} == {"whatsapp_disconnected"}
    assert all("reler o QR Code" in (n.message or "") for n in notifications)
