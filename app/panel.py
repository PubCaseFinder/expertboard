"""Expert panel scheduling.

Expert groups and board members are treated uniformly as "candidates". Each can
be added individually to a patient's expert panel schedule as a participant.
"""

from sqlalchemy import asc

from app.db import Session
from app.models import ExpertBoard
from app.models import ExpertBoardMember
from app.models import PanelParticipant


KIND_GROUP = "group"
KIND_INDIVIDUAL = "individual"


def list_candidates():
    """Return groups and individuals as a single, uniformly-shaped candidate list.

    Each candidate has a ``token`` ("group:<id>" / "individual:<id>") used by the
    add form, so groups and board members can be picked the same way.
    """
    session = Session()
    candidates = []

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

    members = (
        session.query(ExpertBoardMember, ExpertBoard)
        .join(ExpertBoard, ExpertBoardMember.board_id == ExpertBoard.id)
        .order_by(asc(ExpertBoardMember.display_name))
        .all()
    )
    for member, board in members:
        candidates.append(
            {
                "token": f"{KIND_INDIVIDUAL}:{member.id}",
                "kind": KIND_INDIVIDUAL,
                "name": member.display_name,
                "detail": f"{member.role} · {board.name}",
            }
        )

    return candidates


def list_participants(patient_id):
    session = Session()
    return (
        session.query(PanelParticipant)
        .filter(PanelParticipant.patient_id == patient_id)
        .order_by(asc(PanelParticipant.created_at), asc(PanelParticipant.id))
        .all()
    )


def _resolve_token(session, token):
    """Resolve a candidate token into (kind, ref_id, display_name, detail)."""
    if not token or ":" not in token:
        return None
    kind, _, raw_id = token.partition(":")
    if not raw_id.isdigit():
        return None
    ref_id = int(raw_id)

    if kind == KIND_GROUP:
        group = session.get(ExpertBoard, ref_id)
        if group is None:
            return None
        return kind, ref_id, group.name, group.specialty or group.country or "Expert board"

    if kind == KIND_INDIVIDUAL:
        member = session.get(ExpertBoardMember, ref_id)
        if member is None:
            return None
        board = session.get(ExpertBoard, member.board_id)
        board_name = board.name if board else "Board"
        return kind, ref_id, member.display_name, f"{member.role} · {board_name}"

    return None


def add_participant(patient_id, token):
    """Add a group or individual to a patient's panel. Returns (participant, error)."""
    session = Session()
    resolved = _resolve_token(session, token)
    if resolved is None:
        return None, "Please choose a valid group or individual."
    kind, ref_id, display_name, detail = resolved

    existing = (
        session.query(PanelParticipant)
        .filter(PanelParticipant.patient_id == patient_id)
        .filter(PanelParticipant.participant_kind == kind)
        .filter(PanelParticipant.ref_id == ref_id)
        .first()
    )
    if existing is not None:
        return None, f"{display_name} is already on this panel."

    participant = PanelParticipant(
        patient_id=patient_id,
        participant_kind=kind,
        ref_id=ref_id,
        display_name=display_name,
        detail=detail,
    )
    session.add(participant)
    session.commit()
    return participant, None


def remove_participant(patient_id, participant_id):
    """Remove a participant from a patient's panel. Returns True if removed."""
    session = Session()
    participant = session.get(PanelParticipant, participant_id)
    if participant is None or participant.patient_id != patient_id:
        return False
    session.delete(participant)
    session.commit()
    return True
