"""Template setup for the standalone notebook demo."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))
STATIC_ROOT = ROOT / "static"


def static_url(path: str) -> str:
    """Return a path under the public application's static mount."""
    relative = path.lstrip("/")
    try:
        stamp = int((STATIC_ROOT / relative).stat().st_mtime)
    except OSError:
        return f"/static/{relative}"
    return f"/static/{relative}?v={stamp}"


templates.env.globals["static_url"] = static_url
