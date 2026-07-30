import os
import secrets
from functools import wraps

import jwt as pyjwt
from authlib.integrations.flask_client import OAuth
from flask import Blueprint
from flask import current_app
from flask import redirect
from flask import session
from flask import url_for

oauth = OAuth()

auth_bp = Blueprint("auth", __name__)


def init_oauth(app):
    """Wire the app up to Keycloak over OIDC.

    Keycloak is reached two different ways depending on who's asking:
      - the browser must hit the publicly published port (e.g. localhost:8081)
      - this Flask container must reach Keycloak over the Docker network
        (e.g. http://keycloak:8080), since "localhost" inside the app
        container refers to the app container itself, not Keycloak.

    Because of that, we don't use OIDC autodiscovery (server_metadata_url) —
    it would bake in whichever single hostname Keycloak itself was configured
    with, and either the browser redirect or the server-to-server token
    exchange would break. Instead each endpoint is set explicitly below.
    """
    internal_issuer = os.environ.get(
        "EXPERTBOARD_OIDC_ISSUER_INTERNAL",
        "http://keycloak:8080/realms/expertboard",
    ).rstrip("/")
    public_issuer = os.environ.get(
        "EXPERTBOARD_OIDC_ISSUER_PUBLIC",
        "http://localhost:8081/realms/expertboard",
    ).rstrip("/")
    client_id = os.environ.get("EXPERTBOARD_OIDC_CLIENT_ID", "expertboard-app")
    client_secret = os.environ.get("EXPERTBOARD_OIDC_CLIENT_SECRET", "")

    oauth.init_app(app)
    oauth.register(
        name="keycloak",
        client_id=client_id,
        client_secret=client_secret,
        authorize_url=f"{public_issuer}/protocol/openid-connect/auth",
        access_token_url=f"{internal_issuer}/protocol/openid-connect/token",
        userinfo_endpoint=f"{internal_issuer}/protocol/openid-connect/userinfo",
        jwks_uri=f"{internal_issuer}/protocol/openid-connect/certs",
        client_kwargs={"scope": "openid profile email"},
    )

    app.config["EXPERTBOARD_OIDC_PUBLIC_ISSUER"] = public_issuer
    app.config["EXPERTBOARD_OIDC_CLIENT_ID"] = client_id


@auth_bp.route("/login")
def login():
    redirect_uri = os.environ.get("EXPERTBOARD_OIDC_REDIRECT_URI") or url_for(
        "auth.auth_callback", _external=True
    )
    session["oidc_state"] = secrets.token_urlsafe(16)
    return oauth.keycloak.authorize_redirect(redirect_uri, state=session["oidc_state"])


@auth_bp.route("/auth/callback")
def auth_callback():
    token = oauth.keycloak.authorize_access_token()
    claims = _decode_access_token(token.get("access_token"))
    userinfo = token.get("userinfo") or {}

    session["user"] = {
        "sub": claims.get("sub") or userinfo.get("sub"),
        "email": claims.get("email") or userinfo.get("email"),
        "name": claims.get("name")
        or claims.get("preferred_username")
        or userinfo.get("name"),
        "roles": claims.get("realm_access", {}).get("roles", []),
    }
    return redirect(url_for("expertboard.board_list"))


@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("oidc_state", None)

    public_issuer = current_app.config.get("EXPERTBOARD_OIDC_PUBLIC_ISSUER")
    client_id = current_app.config.get("EXPERTBOARD_OIDC_CLIENT_ID")
    post_logout_redirect = url_for("expertboard.board_list", _external=True)

    if not public_issuer:
        return redirect(url_for("expertboard.board_list"))

    return redirect(
        f"{public_issuer}/protocol/openid-connect/logout"
        f"?post_logout_redirect_uri={post_logout_redirect}"
        f"&client_id={client_id}"
    )


def _decode_access_token(access_token):
    """Read claims (email, name, realm roles) out of the access token.

    Signature verification is skipped here on purpose: this token came
    straight from Keycloak's token endpoint over a server-to-server call
    we made ourselves (not something a browser handed us), so there's
    nothing to verify it against an attacker for. If this app ever needs
    to validate tokens presented by a third party (e.g. an external API
    caller), that path must verify the signature against jwks_uri instead.
    """
    if not access_token:
        return {}
    try:
        return pyjwt.decode(access_token, options={"verify_signature": False})
    except pyjwt.PyJWTError:
        return {}


def current_user():
    return session.get("user")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped
