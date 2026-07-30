from flask import Blueprint
from flask import abort
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for

from app import auth
from app import cases
from app import patients
from app import admin
from app import panel
from app import family as family_module


bp = Blueprint("expertboard", __name__)


def _vkey(v):
    """Canonical genomic key for variant matching: chrom:pos:ref:alt"""
    return f"{v.chrom}:{v.pos}:{v.ref}:{v.alt}"


@bp.route("/switch-role", methods=["POST"])
def switch_role():
    auth.set_role(request.form.get("role"))
    next_url = request.form.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("expertboard.board_list"))


@bp.route("/patients")
def patient_list():
    return render_template(
        "patient_list.html",
        r_patients=patients.list_patients(),
        r_review_status_labels=patients.REVIEW_STATUS_LABELS,
    )


@bp.route("/patients/queue")
def patient_queue():
    return render_template(
        "patient_queue.html",
        r_columns=patients.list_patients_by_status(),
    )


@bp.route("/patients/import", methods=["POST"])
def patient_import():
    upload = request.files.get("vcf_file")
    patient_code = (request.form.get("patient_code") or "").strip()
    display_name = (request.form.get("display_name") or "").strip()
    diagnosis_name = (request.form.get("diagnosis_name") or "").strip()

    if not patient_code:
        flash("Patient ID is required.", "error")
        return redirect(url_for("expertboard.patient_list"))
    if upload is None or not upload.filename:
        flash("Please choose a VCF file to upload.", "error")
        return redirect(url_for("expertboard.patient_list"))
    if not patients.is_allowed_filename(upload.filename):
        flash("Unsupported file type. Please upload a .vcf file.", "error")
        return redirect(url_for("expertboard.patient_list"))

    patient, count = patients.import_uploaded_vcf(
        upload, patient_code, display_name, diagnosis_name
    )
    flash(f"Imported {count} variants for {patient.patient_code}.", "success")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient.id))


@bp.route("/patients/<int:patient_id>")
def patient_detail(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    structured_family = family_module.list_family_members(patient_id)

    # Proband variants
    proband_variants = patients.get_patient_variants(patient_id)
    proband_key_map = {_vkey(v): v.id for v in proband_variants}

    # Linked patient variants (deduplicated by patient id)
    linked_variants = {}
    for row in structured_family:
        lp = row.get("linked_patient")
        if lp and lp.id not in linked_variants:
            linked_variants[lp.id] = {
                "patient": lp,
                "relationship_label": row["relationship_label"],
                "variants": patients.get_patient_variants(lp.id),
            }

    # variant_shares: proband variant_id → [relationship_label, ...]
    # shared_vkeys:   set of vkeys present in proband AND at least one linked patient
    variant_shares = {}
    shared_vkeys_set = set()
    for info in linked_variants.values():
        for lv in info["variants"]:
            k = _vkey(lv)
            if k in proband_key_map:
                shared_vkeys_set.add(k)
                variant_shares.setdefault(proband_key_map[k], []).append(
                    info["relationship_label"]
                )

    return render_template(
        "patient_detail.html",
        r_patient=patient,
        r_variants=proband_variants,
        r_variant_shares=variant_shares,
        r_proband_vkeys=list(proband_key_map.keys()),
        r_shared_vkeys=list(shared_vkeys_set),
        r_review_statuses=patients.REVIEW_STATUSES,
        r_review_status_labels=patients.REVIEW_STATUS_LABELS,
        r_review_status_hints=patients.REVIEW_STATUS_HINTS,
        r_expert_groups=admin.list_expert_groups(),
        r_family_members=patients.list_family_members(patient_id),
        r_structured_family=structured_family,
        r_relationships=family_module.RELATIONSHIPS,
        r_affected_options=family_module.AFFECTED_OPTIONS,
        r_linkable_patients=family_module.list_patients_for_linking(),
        r_linked_variants=linked_variants,
    )


@bp.route("/patients/<int:patient_id>/family/members", methods=["POST"])
def patient_family_member_add(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    _member, error = family_module.add_family_member(
        patient_id,
        request.form.get("relationship"),
        request.form.get("display_name"),
        request.form.get("affected"),
        request.form.get("medical_history"),
        request.form.get("linked_patient_id"),
    )
    flash(error or "Family member added.", "error" if error else "success")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient_id))


@bp.route("/patients/<int:patient_id>/family/members/<int:member_id>/remove", methods=["POST"])
def patient_family_member_remove(patient_id, member_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    if family_module.remove_family_member(patient_id, member_id):
        flash("Family member removed.", "success")
    else:
        flash("Family member not found.", "error")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient_id))


@bp.route("/patients/<int:patient_id>/family", methods=["POST"])
def patient_family(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    patients.save_family_info(
        patient_id,
        request.form.get("family_id"),
        request.form.get("family_history"),
    )
    flash("Family information saved.", "success")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient_id))


@bp.route("/patients/<int:patient_id>/expert-group", methods=["POST"])
def patient_expert_group(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    raw = (request.form.get("expert_group_id") or "").strip()
    group_id = int(raw) if raw.isdigit() else None
    patients.set_requested_expert_group(patient_id, group_id)
    flash("Requested expert group updated.", "success")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient_id))


@bp.route("/patients/<int:patient_id>/panel")
def patient_panel(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    return render_template(
        "panel_schedule.html",
        r_patient=patient,
        r_candidates=panel.list_candidates(),
        r_participants=panel.list_participants(patient_id),
    )


@bp.route("/patients/<int:patient_id>/panel/add", methods=["POST"])
def patient_panel_add(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    _participant, error = panel.add_participant(
        patient_id, (request.form.get("participant") or "").strip()
    )
    flash(error or "Participant added to the panel.", "error" if error else "success")
    return redirect(url_for("expertboard.patient_panel", patient_id=patient_id))


@bp.route("/patients/<int:patient_id>/panel/<int:participant_id>/remove", methods=["POST"])
def patient_panel_remove(patient_id, participant_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    if panel.remove_participant(patient_id, participant_id):
        flash("Participant removed from the panel.", "success")
    else:
        flash("Participant not found.", "error")
    return redirect(url_for("expertboard.patient_panel", patient_id=patient_id))


@bp.route("/patients/<int:patient_id>/status", methods=["POST"])
def patient_status(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    status = (request.form.get("review_status") or "").strip()
    if patients.set_review_status(patient_id, status) is None:
        flash("Invalid patient status.", "error")
    else:
        flash("Patient status updated.", "success")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient_id))


@bp.route("/patients/<int:patient_id>/clinical-text", methods=["POST"])
def patient_clinical_text(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    clinical_text = (request.form.get("clinical_text") or "").strip()
    patients.save_clinical_text(patient_id, clinical_text)
    flash("Clinical text saved.", "success")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient_id))


@bp.route("/admin")
def admin_panel():
    return render_template(
        "admin.html",
        r_users=admin.list_users(),
        r_roles=auth.ROLES,
        r_role_labels=auth.ROLE_LABELS,
        r_expert_groups=admin.list_expert_groups(),
        r_boards=admin.list_boards(),
        r_boards_with_members=admin.list_boards_with_members(),
        r_board_groups=admin.BOARD_GROUPS,
        r_member_candidates=admin.list_member_candidates(),
    )


@bp.route("/admin/users", methods=["POST"])
def admin_create_user():
    _user, error = admin.create_user(
        request.form.get("username"),
        request.form.get("display_name"),
        request.form.get("role"),
    )
    flash(error or "User created.", "error" if error else "success")
    return redirect(url_for("expertboard.admin_panel"))


@bp.route("/admin/expert-groups", methods=["POST"])
def admin_create_expert_group():
    _group, error = admin.create_expert_group(
        request.form.get("name"),
        request.form.get("specialty"),
        request.form.get("description"),
    )
    flash(error or "Expert group created.", "error" if error else "success")
    return redirect(url_for("expertboard.admin_panel"))


@bp.route("/admin/board-members", methods=["POST"])
def admin_add_board_member():
    raw_board = (request.form.get("board_id") or "").strip()
    board_id = int(raw_board) if raw_board.isdigit() else None
    _member, error = admin.add_board_member(
        board_id,
        request.form.get("member"),
        request.form.get("board_group"),
    )
    flash(error or "Board member added.", "error" if error else "success")
    return redirect(url_for("expertboard.admin_panel"))


@bp.route("/admin/board-members/<int:member_id>/remove", methods=["POST"])
def admin_remove_board_member(member_id):
    if admin.remove_board_member(member_id):
        flash("Board member removed.", "success")
    else:
        flash("Board member not found.", "error")
    return redirect(url_for("expertboard.admin_panel"))


@bp.route("/boards")
def board_list():
    return render_template("case_list.html", r_boards=cases.list_boards())


@bp.route("/boards/demo", methods=["POST"])
def create_demo_board():
    board, room = cases.ensure_demo_workspace()
    return redirect(url_for("expertboard.room_detail", board_id=board.id, room_id=room.id))


@bp.route("/boards/<int:board_id>")
def board_detail(board_id):
    board_detail = cases.get_board(board_id)
    if board_detail is None:
        abort(404)
    return render_template("board_detail.html", r_board_detail=board_detail)


@bp.route("/boards/<int:board_id>/rooms/<int:room_id>")
def room_detail(board_id, room_id):
    case_detail = cases.get_case_detail(room_id)
    if case_detail is None or case_detail["board"].id != board_id:
        abort(404)
    return render_template("case_detail.html", r_case_detail=case_detail)


@bp.route("/cases")
def case_list():
    return redirect(url_for("expertboard.board_list"))


@bp.route("/cases/demo", methods=["POST"])
def create_demo_case():
    return create_demo_board()


@bp.route("/cases/<int:case_id>")
def case_detail(case_id):
    case_detail = cases.get_case_detail(case_id)
    if case_detail is None:
        abort(404)
    return redirect(
        url_for(
            "expertboard.room_detail",
            board_id=case_detail["board"].id,
            room_id=case_detail["case"].id,
        )
    )

