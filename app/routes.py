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


bp = Blueprint("expertboard", __name__)


@bp.route("/switch-role", methods=["POST"])
def switch_role():
    auth.set_role(request.form.get("role"))
    next_url = request.form.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("expertboard.board_list"))


@bp.route("/patients")
def patient_list():
    return render_template("patient_list.html", r_patients=patients.list_patients())


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
    return render_template(
        "patient_detail.html",
        r_patient=patient,
        r_variants=patients.get_patient_variants(patient_id),
    )


@bp.route("/patients/<int:patient_id>/clinical-text", methods=["POST"])
def patient_clinical_text(patient_id):
    patient = patients.get_patient(patient_id)
    if patient is None:
        abort(404)
    clinical_text = (request.form.get("clinical_text") or "").strip()
    patients.save_clinical_text(patient_id, clinical_text)
    flash("Clinical text saved.", "success")
    return redirect(url_for("expertboard.patient_detail", patient_id=patient_id))


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

