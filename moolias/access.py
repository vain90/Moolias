from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from moolias.mailcow import MailcowAccessDenied, MailcowError


def _accepts_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "").lower()


def _expired_session_needs_login_redirect(request: Request, response: Response) -> bool:
    if not _accepts_html(request):
        return False
    if response.status_code == 401:
        return True
    return request.method not in {"GET", "HEAD", "OPTIONS"} and response.status_code == 403


class AccessRevalidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        email = request.session.get("user_email")
        if not email:
            response = await call_next(request)
            if _expired_session_needs_login_redirect(request, response):
                request.session.clear()
                return RedirectResponse("/", status_code=303)
            return response

        if not request.url.path.startswith("/aliases"):
            return await call_next(request)

        settings = request.app.state.settings
        if not settings.access_tag:
            return await call_next(request)

        try:
            mailbox = await request.app.state.mailcow.get_mailbox(str(email).lower())
        except MailcowAccessDenied:
            request.session.clear()
            return RedirectResponse("/?error=access-denied", status_code=303)
        except MailcowError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)

        # Reuse the mailbox payload in the page request instead of immediately
        # asking Mailcow for the same data again.
        request.state.mailbox = mailbox
        return await call_next(request)
