import os

from dotenv import load_dotenv
from flask import Flask
from flask import flash
from flask import redirect
from flask import request
from flask import url_for
from werkzeug.exceptions import RequestEntityTooLarge

from app.auth import register_roles
from app.db import Session
from app.db import init_db
from app.patients import ensure_schema
from app.admin import ensure_schema as ensure_admin_schema
from app.routes import bp


class _ScriptNameMiddleware:
    """Apply the SCRIPT_NAME env var to each request's WSGI environ.

    Werkzeug's dev server hardcodes SCRIPT_NAME to "" and never reads the
    process environment, so url_for() would otherwise ignore a reverse-proxy
    path prefix (e.g. nginx serving the app under /expertboard/).
    """

    def __init__(self, wsgi_app, script_name):
        self.wsgi_app = wsgi_app
        self.script_name = script_name

    def __call__(self, environ, start_response):
        if self.script_name and not environ.get("SCRIPT_NAME"):
            environ["SCRIPT_NAME"] = self.script_name
        return self.wsgi_app(environ, start_response)


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("EXPERTBOARD_SECRET_KEY", "expertboard-dev")
    # Cap uploads (VCF import) at 10 MB to avoid resource exhaustion.
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    init_db()
    ensure_schema()
    ensure_admin_schema()

    @app.teardown_appcontext
    def _remove_session(_exc):
        Session.remove()

    register_roles(app)
    app.register_blueprint(bp)

    script_name = os.environ.get("SCRIPT_NAME", "")
    if script_name:
        app.wsgi_app = _ScriptNameMiddleware(app.wsgi_app, script_name)

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(_error):
        flash("The uploaded file is too large (max 10 MB).", "error")
        return redirect(request.referrer or url_for("expertboard.patient_list"))

    @app.route("/")
    def root():
        return redirect(url_for("expertboard.patient_queue"))

    return app
