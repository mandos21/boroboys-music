"""Anonymous, read-only link cards; all private APIs retain their existing auth."""

import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from app.api.deps import DbSession
from app.core.config import get_settings
from app.services.link_previews import Preview, get_preview, render_head
from app.services.preview_images import render_image

router = APIRouter(prefix="/previews", include_in_schema=False)


@router.get("/{round_id}/head", response_class=HTMLResponse)
def preview_head(round_id: str, db: DbSession) -> HTMLResponse:
    preview = Preview() if round_id == "default" else get_preview(db, round_id)
    return HTMLResponse(
        render_head(preview, str(get_settings().app_base_url)),
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


@router.get("/{round_id}/image.png")
def preview_image(round_id: str, request: Request, db: DbSession) -> Response:
    # Recheck visibility before consulting the image cache, even for old ?v= URLs.
    preview = Preview() if round_id == "default" else get_preview(db, round_id)
    # Retrying an unavailable cover can change image bytes without changing the
    # round. Periodically expire validators as well as our rendered-image cache.
    etag = f'"{preview.revision}-{int(time.time() // 300)}"'
    headers = {
        "Cache-Control": f"public, max-age={preview.max_age}, must-revalidate",
        "ETag": etag,
        "X-Robots-Tag": "noindex",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(render_image(preview), media_type="image/png", headers=headers)
