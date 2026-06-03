"""
Google Drive Sync - Admin Routes
Add these routes to CaseHub routes/admin.py or create new file
"""
from flask import Blueprint, render_template, jsonify, request, send_from_directory
from auth import admin_required
from config import settings
import os
import subprocess

gdrive_sync_bp = Blueprint('gdrive_sync', __name__, url_prefix='/admin/gdrive-sync')


@gdrive_sync_bp.route('/')
@admin_required
def admin_page():
    """Google Drive Sync admin page."""
    return render_template('gdrive_sync_admin.html')


@gdrive_sync_bp.route('/api/auto-sync-status')
@admin_required
def auto_sync_status():
    """Check if auto-sync cron job is enabled."""
    try:
        # Check if cron file exists
        cron_file = '/etc/cron.d/gdrive-sync'
        enabled = os.path.exists(cron_file)

        if enabled:
            # Check if it's commented out
            with open(cron_file, 'r') as f:
                content = f.read()
                enabled = not content.strip().startswith('#')

        return jsonify({
            'enabled': enabled,
            'cron_file': cron_file
        })
    except Exception as e:
        return jsonify({
            'enabled': False,
            'error': str(e)
        }), 500


@gdrive_sync_bp.route('/api/auto-sync-toggle', methods=['POST'])
@admin_required
def toggle_auto_sync():
    """Enable or disable auto-sync cron job."""
    try:
        data = request.get_json()
        enabled = data.get('enabled', False)

        cron_file = '/etc/cron.d/gdrive-sync'
        cron_content = f'''# Google Drive Sync - Auto sync every 6 hours
0 */6 * * * root cd {settings.BASE_DIR} && venv/bin/python3 scripts/bulk_sync_from_drive.py >> /var/log/gdrive-sync.log 2>&1
'''

        if enabled:
            # Create/enable cron job
            with open(cron_file, 'w') as f:
                f.write(cron_content)
            os.chmod(cron_file, 0o644)
            message = 'Auto-sync enabled'
        else:
            # Disable by commenting out
            if os.path.exists(cron_file):
                with open(cron_file, 'w') as f:
                    f.write('# ' + cron_content.replace('\n', '\n# '))
            message = 'Auto-sync disabled'

        return jsonify({
            'success': True,
            'enabled': enabled,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@gdrive_sync_bp.route('/api/run-manual-sync', methods=['POST'])
@admin_required
def run_manual_sync():
    """Run bulk sync manually in background."""
    try:
        data = request.get_json()
        max_clients = data.get('max_clients', None)

        # Run script in background (no shell=True — use subprocess safely)
        venv_python = os.path.join(settings.BASE_DIR, 'venv', 'bin', 'python3')
        script = os.path.join(settings.BASE_DIR, 'scripts', 'bulk_sync_from_drive.py')
        cmd = [venv_python, script]

        if max_clients:
            cmd.extend(['--max-clients', str(max_clients)])

        log_file = open('/tmp/gdrive_manual_sync.log', 'w')
        subprocess.Popen(cmd, cwd=settings.BASE_DIR, stdout=log_file, stderr=log_file)

        return jsonify({
            'success': True,
            'message': 'Manual sync started in background',
            'log_file': '/tmp/gdrive_manual_sync.log'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@gdrive_sync_bp.route('/static/gdrive_sync_ui.js')
def serve_js():
    """Serve the UI JavaScript file."""
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), '../static'),
        'gdrive_sync_ui.js',
        mimetype='application/javascript'
    )


# Register blueprint in app.py:
# from routes.gdrive_sync_routes import gdrive_sync_bp
# app.register_blueprint(gdrive_sync_bp)
