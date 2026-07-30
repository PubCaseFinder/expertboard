"""Lightweight role model for the hackathon prototype.

There is no real authentication yet. Instead we keep a single "active role" in
the session so the UI can demonstrate how operations differ per role. A top-bar
switcher lets you flip between roles to see which edit permissions each one has.
Nothing here blocks access to data - it only drives what the UI shows as
allowed vs. disallowed.
"""

from flask import session


DEFAULT_ROLE = "viewer"

# Ordered list of roles shown in the switcher.
ROLES = ["viewer", "clinician", "bioinformatician", "admin"]

ROLE_LABELS = {
    "viewer": "Viewer",
    "clinician": "Clinician",
    "bioinformatician": "Bioinformatician",
    "admin": "Administrator",
}

# Capability key -> human-readable label. These are the "edit permissions"
# surfaced in the UI so a reviewer can see what the active role is allowed to do.
CAPABILITIES = [
    ("view", "View"),
    ("edit_phenotype", "Edit phenotype"),
    ("edit_variant", "Edit variant interpretation"),
    ("edit_consensus", "Edit consensus / final decision"),
    ("manage_board", "Manage board & members"),
]

CAPABILITY_LABELS = dict(CAPABILITIES)

ROLE_CAPABILITIES = {
    "viewer": {"view"},
    "clinician": {"view", "edit_phenotype", "edit_consensus"},
    "bioinformatician": {"view", "edit_variant"},
    "admin": {"view", "edit_phenotype", "edit_variant", "edit_consensus", "manage_board"},
}


def current_role():
    role = session.get("role", DEFAULT_ROLE)
    if role not in ROLE_CAPABILITIES:
        return DEFAULT_ROLE
    return role


def set_role(role):
    if role in ROLE_CAPABILITIES:
        session["role"] = role
        return True
    return False


def current_user_id():
    """Return the selected user id from the session, or None."""
    raw = session.get("user_id")
    return int(raw) if raw else None


def set_current_user(user_id):
    """Store the acting user id in the session."""
    session["user_id"] = int(user_id) if user_id else None


def current_user_display():
    """Return a display label for the current acting user.

    Used to auto-stamp assessments and other audit actions.
    Falls back to the role label if no specific user is selected.
    """
    uid = current_user_id()
    if uid:
        from app.db import Session as DbSession  # lazy — avoids circular import
        from app.models import User
        user = DbSession().get(User, uid)
        if user:
            return user.display_name
    return ROLE_LABELS.get(current_role(), current_role())


def capabilities_for(role):
    return ROLE_CAPABILITIES.get(role, set())


def has_capability(capability, role=None):
    role = role or current_role()
    return capability in capabilities_for(role)


def register_roles(app):
    """Expose role state and helpers to every template."""

    @app.context_processor
    def _inject_roles():
        role = current_role()
        uid = current_user_id()

        # Lazy imports to avoid module-level circular dependencies
        from app.db import Session as DbSession
        from app.models import User
        db_s = DbSession()
        acting_user = db_s.get(User, uid) if uid else None
        all_users = db_s.query(User).order_by(User.display_name).all()

        return {
            "current_role": role,
            "role_labels": ROLE_LABELS,
            "roles": ROLES,
            "capabilities": CAPABILITIES,
            "capability_labels": CAPABILITY_LABELS,
            "role_capabilities": ROLE_CAPABILITIES,
            "has_capability": has_capability,
            "current_user_id": uid,
            "acting_user": acting_user,
            "all_users": all_users,
        }
