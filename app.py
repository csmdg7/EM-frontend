"""
app.py
======
ECHOMARK Intel Portal — Flask application factory.
"""

print("[ECHOMARK][app.py] Starting ECHOMARK application factory")

import os
from dotenv import load_dotenv

# MUST run before any server.* import — several scanner modules read
# os.environ.get(...) at import time (module-level constants), so if
# .env isn't loaded first, those keys are permanently baked in as "".
_env_path = os.path.join(os.path.dirname(__file__), ".env")
_loaded   = load_dotenv(dotenv_path=_env_path)
print(f"[ECHOMARK][app.py] load_dotenv: path={_env_path} loaded={_loaded}")

from flask import Flask, send_from_directory

from server.storage.cases import migrate_flat_files
from server.storage.users import seed_admin_user
from server.routes.auth  import auth_bp
from server.routes.cases import cases_bp
from server.routes.intel import intel_bp


def create_app() -> Flask:
    print("[ECHOMARK][app.py] create_app: initializing Flask")
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = os.environ.get("SECRET_KEY", "echomark-secret-key-2026")
    app.url_map.strict_slashes = False

    # Register blueprints
    app.register_blueprint(auth_bp,  url_prefix="/api/auth")
    app.register_blueprint(cases_bp, url_prefix="/api/cases")
    app.register_blueprint(intel_bp, url_prefix="/api")
    print("[ECHOMARK][app.py] create_app: blueprints registered (auth, cases, intel)")

    # SPA catch-all
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        if path.startswith("api/") or path.startswith("static/"):
            from flask import abort
            abort(404)
        return send_from_directory(app.template_folder, "index.html")

    # Startup tasks
    with app.app_context():
        print("[ECHOMARK][app.py] create_app: running startup tasks")
        migrate_flat_files()
        seed_admin_user()
        print("[ECHOMARK][app.py] create_app: startup tasks complete")

    print("[ECHOMARK][app.py] create_app: app ready")
    return app


print("[ECHOMARK][app.py] Module ready — Flask app factory registered")

if __name__ == "__main__":
    app  = create_app()
    port = int(os.environ.get("PORT", 3000))
    print(f"[ECHOMARK][app.py] Server starting on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
    print(f"[ECHOMARK][app.py] Server stopped")
