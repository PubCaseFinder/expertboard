from sqlalchemy import ForeignKey
from sqlalchemy import Text
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.types import String
from sqlalchemy.types import TIMESTAMP

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    diagnosis_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vcf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clinical_text_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clinical_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    chrom: Mapped[str] = mapped_column(String(16), nullable=False)
    pos: Mapped[int] = mapped_column(nullable=False)
    variant_ext_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)
    alt: Mapped[str] = mapped_column(String(255), nullable=False)
    gene: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hgvs_c: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hgvs_p: Mapped[str | None] = mapped_column(String(128), nullable=True)
    variant_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    clin_sig: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    genotype: Mapped[str | None] = mapped_column(String(16), nullable=True)
    depth: Mapped[int | None] = mapped_column(nullable=True)
    genotype_quality: Mapped[int | None] = mapped_column(nullable=True)
    quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    filter_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_info: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())


class ExpertBoard(Base):
    __tablename__ = "expert_boards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class ExpertBoardMember(Base):
    __tablename__ = "expert_board_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    board_id: Mapped[int] = mapped_column(ForeignKey(ExpertBoard.id), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    board_group: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    board_id: Mapped[int | None] = mapped_column(ForeignKey(ExpertBoard.id), nullable=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    suspected_diseases: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phenotypes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    genes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variants: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class CaseMember(Base):
    __tablename__ = "case_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey(Case.id), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    board_group: Mapped[str] = mapped_column(String(32), nullable=False)
    stance: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey(Case.id), nullable=False)
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    author_role: Mapped[str] = mapped_column(String(64), nullable=False)
    comment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="discussion")
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey(Case.id), nullable=False, unique=True)
    current_interpretation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consensus_level: Mapped[str] = mapped_column(String(32), nullable=False, default="in_review")
    supported_count: Mapped[int] = mapped_column(nullable=False, default=4)
    total_count: Mapped[int] = mapped_column(nullable=False, default=5)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey(Case.id), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(), nullable=False, server_default=func.current_timestamp())
