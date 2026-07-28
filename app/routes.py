from flask import Blueprint
from flask import abort
from flask import redirect
from flask import render_template
from flask import url_for

from app import cases


bp = Blueprint("expertboard", __name__)


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

