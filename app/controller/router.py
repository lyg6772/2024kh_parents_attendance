from fastapi import APIRouter
from app.controller.login import login_template, login_post
from app.controller.attendee import attendee_get_default

router = APIRouter()

router.add_api_route("/login", login_template, methods=["get"])
router.add_api_route("/login/request", login_post, methods=["post"])
router.add_api_route("/attendee", attendee_get_default, methods=["get"])
router.add_api_route("/attendee/{cal_date}", attendee_get_default, methods=["get"])