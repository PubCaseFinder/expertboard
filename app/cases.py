from sqlalchemy import desc
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import Session
from app.models import AuditLog
from app.models import Case
from app.models import CaseMember
from app.models import Comment
from app.models import Decision
from app.models import ExpertBoard
from app.models import ExpertBoardMember
from app.pubcasefinder_client import PubCaseFinderClient


DEMO_BOARD_NAME = "Neuromuscular Disease Expert Board"
DEMO_ROOM_TITLE = "Undiagnosed neuromuscular case"
DEMO_BOARDS = [
    {
        "name": "Neuromuscular Disease Expert Board",
        "scope_type": "Disease-focused board",
        "scope": "Congenital myopathy / mitochondrial disease / neuromuscular disorders",
        "description": (
            "A reusable Expert Board for neuromuscular and mitochondrial disease case review. "
            "Individual Review Rooms are opened under this board for specific cases."
        ),
    },
    {
        "name": "ABCA4 Expert Board",
        "scope_type": "Gene-focused board",
        "scope": "ABCA4 / inherited retinal disease / Stargardt disease",
        "description": (
            "A reusable Expert Board for ABCA4-related retinal disease review, with a focus on phenotype fit, "
            "variant interpretation, and family-level evidence."
        ),
    },
    {
        "name": "Mitochondrial Disease Expert Board",
        "scope_type": "Disease-focused board",
        "scope": "Mitochondrial disease / metabolic myopathy",
        "description": (
            "A reusable Expert Board for mitochondrial and metabolic presentations where phenotype, "
            "segregation, biochemical, and genomic evidence must be reviewed together."
        ),
    },
]
DEMO_ROOMS = [
    {
        "board_name": "Neuromuscular Disease Expert Board",
        "title": "Undiagnosed neuromuscular case",
        "status": "in_review",
        "suspected_diseases": "Congenital myopathy, mitochondrial disease",
        "phenotypes": "HP:0001250, HP:0002376, HP:0003202, HP:0001638",
        "genes": "ACTA1, RYR1, MT-ATP6",
        "variants": "RYR1 c.14582G>A, ACTA1 c.350A>G",
        "summary": "Synthetic seed case review room for phenotype, variant, hypothesis, and consensus review.",
        "interpretation": "Current diagnostic direction remains neuromuscular disease with RYR1/ACTA1 under review.",
        "supported_count": 4,
        "total_count": 5,
    },
    {
        "board_name": "Mitochondrial Disease Expert Board",
        "title": "Mitochondrial disease differential review",
        "status": "triage",
        "suspected_diseases": "Mitochondrial disease, metabolic myopathy",
        "phenotypes": "HP:0003202, HP:0001324, HP:0001947, HP:0001251",
        "genes": "MT-ATP6, POLG, TWNK",
        "variants": "MT-ATP6 m.8993T>G, POLG c.1399G>A",
        "summary": "A second synthetic room showing how the same expert board can triage a different case.",
        "interpretation": "Mitochondrial disease remains plausible; the board needs segregation and biochemical evidence.",
        "supported_count": 3,
        "total_count": 5,
    },
    {
        "board_name": "Neuromuscular Disease Expert Board",
        "title": "RYR1 and ACTA1 variant interpretation",
        "status": "evidence_review",
        "suspected_diseases": "RYR1-related myopathy, ACTA1-related myopathy",
        "phenotypes": "HP:0003808, HP:0003551, HP:0001252, HP:0003324",
        "genes": "RYR1, ACTA1",
        "variants": "RYR1 c.11798A>G, ACTA1 c.541C>T",
        "summary": "A variant-focused review room for comparing ACMG-style evidence and clinical fit.",
        "interpretation": "Variant evidence is under review; phenotype fit is stronger for RYR1 than ACTA1.",
        "supported_count": 2,
        "total_count": 5,
    },
    {
        "board_name": "ABCA4 Expert Board",
        "title": "ABCA4 retinal dystrophy variant review",
        "status": "evidence_review",
        "suspected_diseases": "ABCA4-related retinopathy, inherited retinal dystrophy",
        "phenotypes": "HP:0000510, HP:0000546, HP:0007754, HP:0007703",
        "genes": "ABCA4, PRPH2, PROM1",
        "variants": "ABCA4 c.6764G>T, ABCA4 c.5882G>A",
        "summary": "A retinal disease review room for ClinGen-inspired variant interpretation and phenotype fit.",
        "interpretation": "ABCA4 remains the leading gene; benign and pathogenic evidence need board-level review.",
        "supported_count": 3,
        "total_count": 5,
    },
]

CORE_MEMBERS = [
    ("Case chair", "case_chair", "Support"),
    ("Clinical reviewer", "clinical_reviewer", "Support"),
    ("Bioinformatician", "bioinformatician", "Conditional"),
    ("Laboratory scientist", "laboratory_scientist", "Support"),
    ("Genetic counselor", "genetic_counselor", "Support"),
]

OPTIONAL_MEMBERS = [
    ("Case coordinator", "case_coordinator", "Tracking"),
    ("External consultant", "external_consultant", "Pending"),
]

STATUS_LABELS = {
    "triage": "Triage",
    "in_review": "In review",
    "evidence_review": "Evidence review",
    "consensus_ready": "Consensus ready",
    "closed": "Closed",
}


def _short_text(text, max_length=130):
    if not text:
        return ""
    compact = " ".join(str(text).split())
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 1] + "..."


def _status_label(status):
    return STATUS_LABELS.get(status, str(status).replace("_", " ").title())


def _ensure_case_board_id_column(session):
    try:
        session.execute(text("ALTER TABLE cases ADD COLUMN board_id INT NULL"))
        session.commit()
    except OperationalError:
        session.rollback()


def _ensure_demo_board(session, board_data):
    board = session.query(ExpertBoard).filter(ExpertBoard.name == board_data["name"]).first()
    if board:
        board.scope_type = board_data["scope_type"]
        board.scope = board_data["scope"]
        board.description = board_data["description"]
        board.status = "active"
        return board

    if board_data["name"] == "ABCA4 Expert Board":
        legacy_board = session.query(ExpertBoard).filter(ExpertBoard.name == "Retinal Dystrophy Expert Board").first()
        if legacy_board:
            legacy_board.name = board_data["name"]
            legacy_board.scope_type = board_data["scope_type"]
            legacy_board.scope = board_data["scope"]
            legacy_board.description = board_data["description"]
            legacy_board.status = "active"
            return legacy_board

    board = ExpertBoard(
        name=board_data["name"],
        scope_type=board_data["scope_type"],
        scope=board_data["scope"],
        description=board_data["description"],
        status="active",
    )
    session.add(board)
    session.flush()

    for display_name, role, _stance in CORE_MEMBERS:
        session.add(
            ExpertBoardMember(
                board_id=board.id,
                display_name=display_name,
                role=role,
                board_group="core",
                status="active",
            )
        )
    for display_name, role, _stance in OPTIONAL_MEMBERS:
        session.add(
            ExpertBoardMember(
                board_id=board.id,
                display_name=display_name,
                role=role,
                board_group="optional",
                status="available",
            )
        )
    return board


def _ensure_demo_boards(session):
    return {
        board_data["name"]: _ensure_demo_board(session, board_data)
        for board_data in DEMO_BOARDS
    }


def _create_room_artifacts(session, room, room_data):
    existing_members = session.query(CaseMember).filter(CaseMember.case_id == room.id).first()
    if existing_members:
        return

    for display_name, role, stance in CORE_MEMBERS:
        session.add(
            CaseMember(
                case_id=room.id,
                display_name=display_name,
                role=role,
                board_group="core",
                stance=stance,
                status="active",
            )
        )
    for display_name, role, stance in OPTIONAL_MEMBERS:
        session.add(
            CaseMember(
                case_id=room.id,
                display_name=display_name,
                role=role,
                board_group="optional",
                stance=stance,
                status="available",
            )
        )

    session.add(
        Decision(
            case_id=room.id,
            current_interpretation=room_data["interpretation"],
            consensus_level="supported",
            supported_count=room_data["supported_count"],
            total_count=room_data["total_count"],
        )
    )
    session.add(
        Comment(
            case_id=room.id,
            author_name="Dr. Aki Okahiro",
            author_role="Case chair",
            comment_type="board_note",
            body="Review room created. Core reviewers should confirm phenotype fit and variant evidence before recommendation.",
        )
    )
    session.add(
        AuditLog(
            case_id=room.id,
            actor_name="system",
            actor_role="system",
            action_type="create_demo_review_room",
            target_type="review_room",
            target_id=str(room.id),
        )
    )


def _ensure_demo_room(session, room_data, board):
    existing = session.query(Case).filter(Case.title == room_data["title"]).first()
    if existing:
        if existing.board_id != board.id:
            existing.board_id = board.id
        existing.status = room_data["status"]
        _create_room_artifacts(session, existing, room_data)
        return existing

    room = Case(
        board_id=board.id,
        title=room_data["title"],
        status=room_data["status"],
        suspected_diseases=room_data["suspected_diseases"],
        phenotypes=room_data["phenotypes"],
        genes=room_data["genes"],
        variants=room_data["variants"],
        summary=room_data["summary"],
    )
    session.add(room)
    session.flush()
    _create_room_artifacts(session, room, room_data)
    return room


def ensure_demo_workspace():
    with Session() as session:
        _ensure_case_board_id_column(session)
        boards_by_name = _ensure_demo_boards(session)
        rooms = [
            _ensure_demo_room(session, room_data, boards_by_name[room_data["board_name"]])
            for room_data in DEMO_ROOMS
        ]
        session.commit()
        board = boards_by_name[DEMO_BOARD_NAME]
        return board, rooms[0]


def list_boards():
    with Session() as session:
        _ensure_case_board_id_column(session)
        boards_by_name = _ensure_demo_boards(session)
        for room_data in DEMO_ROOMS:
            _ensure_demo_room(session, room_data, boards_by_name[room_data["board_name"]])
        session.commit()

        boards = session.query(ExpertBoard).order_by(desc(ExpertBoard.updated_at)).all()
        return [
            {
                "board": board,
                "expert_count": (
                    session.query(ExpertBoardMember)
                    .filter(ExpertBoardMember.board_id == board.id)
                    .filter(ExpertBoardMember.board_group == "core")
                    .count()
                ),
                "room_count": session.query(Case).filter(Case.board_id == board.id).count(),
                "summary": _short_text(board.description),
            }
            for board in boards
        ]


def get_board(board_id):
    with Session() as session:
        _ensure_case_board_id_column(session)
        boards_by_name = _ensure_demo_boards(session)
        for room_data in DEMO_ROOMS:
            _ensure_demo_room(session, room_data, boards_by_name[room_data["board_name"]])
        session.commit()

        board = session.query(ExpertBoard).filter(ExpertBoard.id == board_id).first()
        if not board:
            return None
        rooms = session.query(Case).filter(Case.board_id == board.id).order_by(desc(Case.updated_at)).all()
        members = (
            session.query(ExpertBoardMember)
            .filter(ExpertBoardMember.board_id == board.id)
            .order_by(ExpertBoardMember.id.asc())
            .all()
        )
        return {
            "board": board,
            "rooms": [
                {
                    "case": room,
                    "status_label": _status_label(room.status),
                    "summary": _short_text(room.summary or room.suspected_diseases),
                }
                for room in rooms
            ],
            "members": members,
        }


def create_demo_case():
    _board, room = ensure_demo_workspace()
    return room


def list_cases():
    with Session() as session:
        rows = session.query(Case).order_by(desc(Case.updated_at)).all()
        return [
            {
                "case": row,
                "status_label": _status_label(row.status),
                "summary": _short_text(row.summary or row.suspected_diseases),
            }
            for row in rows
        ]


def get_case_detail(case_id):
    client = PubCaseFinderClient()
    with Session() as session:
        _ensure_case_board_id_column(session)
        boards_by_name = _ensure_demo_boards(session)
        for room_data in DEMO_ROOMS:
            _ensure_demo_room(session, room_data, boards_by_name[room_data["board_name"]])
        session.commit()

        case = session.query(Case).filter(Case.id == case_id).first()
        if not case:
            return None
        board = session.query(ExpertBoard).filter(ExpertBoard.id == case.board_id).first()
        if not board:
            board = boards_by_name[DEMO_BOARD_NAME]

        members = (
            session.query(CaseMember)
            .filter(CaseMember.case_id == case_id)
            .order_by(CaseMember.id.asc())
            .all()
        )
        board_members = (
            session.query(ExpertBoardMember)
            .filter(ExpertBoardMember.board_id == board.id)
            .order_by(ExpertBoardMember.id.asc())
            .all()
        )
        comments = (
            session.query(Comment)
            .filter(Comment.case_id == case_id)
            .order_by(desc(Comment.created_at))
            .limit(10)
            .all()
        )
        decision = session.query(Decision).filter(Decision.case_id == case_id).first()
        audit_logs = (
            session.query(AuditLog)
            .filter(AuditLog.case_id == case_id)
            .order_by(desc(AuditLog.created_at))
            .limit(12)
            .all()
        )

        core_positions = [
            {
                "role": member.display_name,
                "stance": member.stance,
                "tone": "conditional" if member.stance == "Conditional" else "support",
            }
            for member in members
            if member.board_group == "core"
        ]
        optional_support = [
            {
                "role": member.display_name,
                "stance": member.stance,
                "tone": "optional",
            }
            for member in members
            if member.board_group == "optional"
        ]
        supported = decision.supported_count if decision else 0
        total = decision.total_count if decision else 5
        percent = round((supported / total) * 100) if total else 0

        return {
            "board": board,
            "board_members": board_members,
            "case": case,
            "status_label": _status_label(case.status),
            "clinical_diagnoses": "Undiagnosed neuromuscular disorder",
            "final_diagnoses": "Not entered",
            "members": members,
            "comments": comments,
            "decision": decision,
            "audit_logs": audit_logs,
            "core_positions": core_positions,
            "optional_support": optional_support,
            "positions": core_positions + optional_support,
            "consensus": {"supported": supported, "total": total, "percent": percent},
            "pubcasefinder": client.health_hint(),
            "phenotype_hints": [item.strip() for item in (case.phenotypes or "").split(",") if item.strip()],
            "evidence_cards": [
                {
                    "title": "Phenotype coherence",
                    "detail": "Core HPO set points to a neuromuscular presentation with early motor involvement.",
                    "tag": "Clinical",
                },
                {
                    "title": "Gene shortlist",
                    "detail": "ACTA1 and RYR1 remain leading discussion genes from the current intake package.",
                    "tag": "Bioinformatics",
                },
                {
                    "title": "Diagnostic support signal",
                    "detail": "External matching signals are treated as evidence inputs, not final decisions.",
                    "tag": "Evidence",
                },
            ],
            "tasks": [
                {"title": "Confirm ACMG framing for shortlist", "owner": "Bioinformatician", "status": "In progress"},
                {"title": "Prepare family history summary", "owner": "Case coordinator", "status": "Ready"},
                {"title": "Draft board recommendation", "owner": "Case chair", "status": "Pending"},
            ],
        }
