"""Admin data access: users, expert groups, and board members.

These screens back the administrator's editing area. There is no real access
control in this hackathon build; the admin UI is simply shown to whoever holds
the "manage_board" capability via the role switcher.
"""

from sqlalchemy import asc
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.auth import ROLES
from app.auth import ROLE_LABELS
from app.db import Session
from app.models import AppSetting
from app.models import ExpertBoard
from app.models import ExpertBoardMember
from app.models import User


# Mock placeholder; this build has no login, so no real password is stored.
MOCK_PASSWORD_HASH = "mock-no-login"

BOARD_GROUPS = ["core", "optional"]

KIND_USER = "user"
KIND_GROUP = "group"


OLLAMA_URL_KEY = "ollama_base_url"
OLLAMA_MODEL_KEY = "ollama_model"
OLLAMA_API_KEY_KEY = "ollama_api_key"

DEFAULT_OLLAMA_MODEL = "llama3"


def ensure_schema():
    """Add columns and tables introduced after the initial table creation."""
    _add_member_column_if_missing("member_kind VARCHAR(16) NULL")
    _add_member_column_if_missing("ref_id INT NULL")
    _add_board_column_if_missing("country VARCHAR(64) NULL")
    _add_board_column_if_missing("specialty VARCHAR(160) NULL")
    _add_table_column_if_missing("variant_assessments", "expert_board_id INT NULL")
    _add_table_column_if_missing("variant_assessments", "acmg_codes VARCHAR(255) NULL")
    _add_table_column_if_missing("patients", "requested_expert_board_id INT NULL")
    _add_table_column_if_missing("variants", "llm_score INT NULL")
    _add_table_column_if_missing("variants", "llm_reason TEXT NULL")
    _create_app_settings_if_missing()


def _add_member_column_if_missing(column_definition):
    session = Session()
    try:
        session.execute(
            text(f"ALTER TABLE expert_board_members ADD COLUMN {column_definition}")
        )
        session.commit()
    except OperationalError:
        session.rollback()


def _add_board_column_if_missing(column_definition):
    session = Session()
    try:
        session.execute(
            text(f"ALTER TABLE expert_boards ADD COLUMN {column_definition}")
        )
        session.commit()
    except OperationalError:
        session.rollback()


def _add_group_column_if_missing(column_definition):
    """Legacy helper kept for compatibility — no-op if expert_groups exists."""
    session = Session()
    try:
        session.execute(
            text(f"ALTER TABLE expert_groups ADD COLUMN {column_definition}")
        )
        session.commit()
    except OperationalError:
        session.rollback()


def _add_table_column_if_missing(table, column_definition):
    session = Session()
    try:
        session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_definition}"))
        session.commit()
    except OperationalError:
        session.rollback()


def _create_app_settings_if_missing():
    session = Session()
    try:
        session.execute(text(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "  `key` VARCHAR(64) NOT NULL PRIMARY KEY,"
            "  `value` TEXT NULL,"
            "  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            "  ON UPDATE CURRENT_TIMESTAMP"
            ")"
        ))
        session.commit()
    except OperationalError:
        session.rollback()


# ---------------------------------------------------------------------------
# App settings (key-value)
# ---------------------------------------------------------------------------

def get_setting(key, default=None):
    session = Session()
    row = session.get(AppSetting, key)
    if row is None:
        return default
    return row.value if row.value is not None else default


def set_setting(key, value):
    session = Session()
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    session.commit()


def get_ollama_settings():
    return {
        "base_url": get_setting(OLLAMA_URL_KEY, ""),
        "model": get_setting(OLLAMA_MODEL_KEY, DEFAULT_OLLAMA_MODEL),
        "api_key": get_setting(OLLAMA_API_KEY_KEY, ""),
    }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def list_users():
    session = Session()
    return session.query(User).order_by(asc(User.username)).all()


def create_user(username, display_name, role):
    """Create a mock user. Returns (user, error_message)."""
    username = (username or "").strip()
    display_name = (display_name or "").strip()
    role = (role or "").strip()

    if not username:
        return None, "Username is required."
    if not display_name:
        return None, "Display name is required."
    if role not in ROLES:
        return None, "Please choose a valid role."

    session = Session()
    existing = session.query(User).filter(User.username == username).first()
    if existing is not None:
        return None, f"User '{username}' already exists."

    user = User(
        username=username,
        display_name=display_name,
        password_hash=MOCK_PASSWORD_HASH,
        role=role,
        status="active",
    )
    session.add(user)
    session.commit()
    return user, None


# ---------------------------------------------------------------------------
# Expert boards (unified — former ExpertGroup merged here)
# ---------------------------------------------------------------------------
def list_expert_groups():
    """Alias kept for template/route compatibility — returns all ExpertBoards."""
    return list_boards()


def create_expert_group(name, specialty, description, country=None):
    """Create an ExpertBoard (the ExpertGroup concept is now merged into Board)."""
    name = (name or "").strip()
    specialty = (specialty or "").strip()
    description = (description or "").strip()
    country = (country or "").strip()

    if not name:
        return None, "Group name is required."

    session = Session()
    existing = session.query(ExpertBoard).filter(ExpertBoard.name == name).first()
    if existing is not None:
        return None, f"Expert board '{name}' already exists."

    board = ExpertBoard(
        name=name,
        scope_type="specialty",
        scope=specialty or name,
        country=country or None,
        specialty=specialty or None,
        description=description or None,
        status="active",
    )
    session.add(board)
    session.commit()
    return board, None


# ---------------------------------------------------------------------------
# Board members
# ---------------------------------------------------------------------------
def list_boards():
    session = Session()
    return session.query(ExpertBoard).order_by(asc(ExpertBoard.name)).all()


def list_boards_with_members():
    session = Session()
    boards = session.query(ExpertBoard).order_by(asc(ExpertBoard.name)).all()
    rows = []
    for board in boards:
        members = (
            session.query(ExpertBoardMember)
            .filter(ExpertBoardMember.board_id == board.id)
            .order_by(asc(ExpertBoardMember.id))
            .all()
        )
        rows.append({"board": board, "members": members})
    return rows


def list_member_candidates():
    """Return created users and expert groups as one selectable candidate list.

    Each candidate has a ``token`` ("user:<id>" / "group:<id>") so board members
    can be picked from existing users and groups instead of free text.
    """
    session = Session()
    candidates = []

    users = session.query(User).order_by(asc(User.display_name)).all()
    for user in users:
        candidates.append(
            {
                "token": f"{KIND_USER}:{user.id}",
                "kind": KIND_USER,
                "name": user.display_name,
                "detail": ROLE_LABELS.get(user.role, user.role),
            }
        )

    groups = session.query(ExpertBoard).order_by(asc(ExpertBoard.name)).all()
    for group in groups:
        candidates.append(
            {
                "token": f"{KIND_GROUP}:{group.id}",
                "kind": KIND_GROUP,
                "name": group.name,
                "detail": group.specialty or group.country or "Expert board",
            }
        )

    return candidates


def _resolve_member_token(session, token):
    """Resolve a candidate token into (kind, ref_id, display_name, role)."""
    if not token or ":" not in token:
        return None
    kind, _, raw_id = token.partition(":")
    if not raw_id.isdigit():
        return None
    ref_id = int(raw_id)

    if kind == KIND_USER:
        user = session.get(User, ref_id)
        if user is None:
            return None
        return kind, ref_id, user.display_name, ROLE_LABELS.get(user.role, user.role)

    if kind == KIND_GROUP:
        group = session.get(ExpertBoard, ref_id)
        if group is None:
            return None
        return kind, ref_id, group.name, group.specialty or group.country or "Expert board"

    return None


def add_board_member(board_id, token, board_group):
    """Add an existing user or group to an expert board. Returns (member, error)."""
    board_group = (board_group or "").strip()
    if not board_id:
        return None, "Please choose a board."
    if board_group not in BOARD_GROUPS:
        board_group = "core"

    session = Session()
    board = session.get(ExpertBoard, board_id)
    if board is None:
        return None, "Selected board was not found."

    resolved = _resolve_member_token(session, token)
    if resolved is None:
        return None, "Please choose an existing user or group."
    kind, ref_id, display_name, role = resolved

    existing = (
        session.query(ExpertBoardMember)
        .filter(ExpertBoardMember.board_id == board_id)
        .filter(ExpertBoardMember.member_kind == kind)
        .filter(ExpertBoardMember.ref_id == ref_id)
        .first()
    )
    if existing is not None:
        return None, f"{display_name} is already on this board."

    member = ExpertBoardMember(
        board_id=board_id,
        display_name=display_name,
        role=role,
        board_group=board_group,
        member_kind=kind,
        ref_id=ref_id,
        status="active" if board_group == "core" else "available",
    )
    session.add(member)
    session.commit()
    return member, None


def remove_board_member(member_id):
    """Remove a board member. Returns True if removed."""
    session = Session()
    member = session.get(ExpertBoardMember, member_id)
    if member is None:
        return False
    session.delete(member)
    session.commit()
    return True
