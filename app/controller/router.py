from fastapi import APIRouter
from app.controller.login import login_template

router = APIRouter()

router.add_api_route("/login", login_template, methods=["get"])