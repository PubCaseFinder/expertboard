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
        return {
            "current_role": role,
            "role_labels": ROLE_LABELS,
            "roles": ROLES,
            "capabilities": CAPABILITIES,
            "capability_labels": CAPABILITY_LABELS,
            "role_capabilities": ROLE_CAPABILITIES,
            "has_capability": has_capability,
        }
