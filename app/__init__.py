import os

from dotenv import load_dotenv
from flask import Flask
from flask import redirect
from flask import url_for

from app.auth import auth_bp
from app.auth import init_oauth
from app.db import init_db
from app.routes import bp


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("EXPERTBOARD_SECRET_KEY", "expertboard-dev")

    init_db()
    init_oauth(app)
    app.register_blueprint(bp)
    app.register_blueprint(auth_bp)

    @app.route("/")
    def root():
        return redirect(url_for("expertboard.board_list"))

    return app
