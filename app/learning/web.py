"""Standalone browser shell for the authenticated learning workspace."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..web import templates

router = APIRouter(prefix="/learn", tags=["learning-pages"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def learning_home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="learning/index.html",
        context={"focus_login": False},
    )


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def learning_login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="learning/index.html",
        context={"focus_login": True},
    )
