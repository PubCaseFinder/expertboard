import os

from dotenv import load_dotenv
from flask import Flask
from flask import flash
from flask import redirect
from flask import request
from flask import url_for
from werkzeug.exceptions import RequestEntityTooLarge

from app.auth import register_roles
from app.db import init_db
from app.patients import ensure_schema
from app.admin import ensure_schema as ensure_admin_schema
from app.routes import bp


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("EXPERTBOARD_SECRET_KEY", "expertboard-dev")
    # Cap uploads (VCF import) at 10 MB to avoid resource exhaustion.
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    init_db()
    ensure_schema()
    ensure_admin_schema()

    register_roles(app)
    app.register_blueprint(bp)

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(_error):
        flash("The uploaded file is too large (max 10 MB).", "error")
        return redirect(request.referrer or url_for("expertboard.patient_list"))

    @app.route("/")
    def root():
        return redirect(url_for("expertboard.patient_queue"))

    return app
