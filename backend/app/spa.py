"""Static file serving for the built single-page frontend."""
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    """StaticFiles that answers client-side routes with ``index.html``.

    Only ``/`` maps to a real file; ``/study``, ``/items?type=word`` and the
    rest exist only in the React router. Plain ``StaticFiles`` 404s them, so
    any reload on those pages broke — including the one a mobile browser does
    unprompted when it restores a tab it discarded in the background.

    Misses that can't be a page route still 404: unmatched ``/api/...`` paths
    (a client bug should fail loudly, not receive HTML) and anything that looks
    like a file (a missing asset shouldn't be answered with a page either).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # `path` arrives OS-normalised — backslash-separated on Windows.
            segments = path.replace("\\", "/").split("/")
            if exc.status_code != 404 or segments[0] == "api" or "." in segments[-1]:
                raise
            return await super().get_response("index.html", scope)
