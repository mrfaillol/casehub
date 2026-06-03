from services import leads_manager
from routes import leads
from core.template_config import templates


def test_save_leads_creates_runtime_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    leads_file = data_dir / "leads_crm.json"
    backup_dir = data_dir / "backups"
    monkeypatch.setattr(leads_manager, "DATA_DIR", data_dir)
    monkeypatch.setattr(leads_manager, "LEADS_FILE", leads_file)
    monkeypatch.setattr(leads_manager, "BACKUP_DIR", backup_dir)

    data = leads_manager.load_leads()
    leads_manager.create_lead(data, {"name": "QA Lead", "source": "MANUAL"})
    leads_manager.save_leads(data)

    loaded = leads_manager.load_leads()

    assert leads_file.exists()
    assert backup_dir.exists()
    assert loaded["leads"]


def test_leads_page_uses_shared_configured_templates():
    assert leads.templates is templates
    assert "asset_url" in leads.templates.env.globals
