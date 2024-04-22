from fastapi import APIRouter
from app.controller.login import login_template, login_post

router = APIRouter()

router.add_api_route("/login", login_template, methods=["get"])
router.add_api_route("/login/request", login_post, methods=["post"])