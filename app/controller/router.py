from fastapi import APIRouter
from app.controller.login import login_template, login_post
from app.controller.attendee import attendee_get_default, attendee_get_year_month
from app.controller.admin import admin_attendee_get_year_month, admin_attendee_get_default, admin_attendee_post

router = APIRouter()

router.add_api_route("/login", login_template, methods=["get"])
router.add_api_route("/login/request", login_post, methods=["post"])
router.add_api_route("/attendee", attendee_get_default, methods=["get"])
router.add_api_route("/attendee/{cal_date}", attendee_get_year_month, methods=["get"])
router.add_api_route("/admin/attendee", admin_attendee_get_default, methods=["get"])
router.add_api_route("/admin/attendee", admin_attendee_post, methods=["post"])
router.add_api_route("/admin/attendee/{cal_date}", admin_attendee_get_year_month, methods=["get"])