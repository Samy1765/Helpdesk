"""
Precision AI - HTTP hardening middleware (pure ASGI, so streaming bodies are handled correctly).

  SecurityHeaders  CSP, nosniff, frame denial, referrer and permissions policy; HSTS when served over HTTPS
  BodySizeLimit    413 for bodies over the limit, whether or not the client declared Content-Length
"""

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The SPA bundle is self-contained: no inline or third-party script, fonts are self-hosted. `data:` images are
# used for small inline SVG icons in CSS; `blob:` for attachment downloads.
APP_CSP = "; ".join([
    "default-src 'self'", "script-src 'self'", "style-src 'self'", "img-src 'self' data: blob:",
    "font-src 'self'", "connect-src 'self'", "object-src 'none'", "base-uri 'self'", "form-action 'self'",
    "frame-ancestors 'none'",
])
# FastAPI's Swagger UI / ReDoc pages use an inline bootstrap script and CDN assets.
DOCS_CSP = "; ".join([
    "default-src 'self'", "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly", "font-src 'self' https://fonts.gstatic.com",
    "worker-src 'self' blob:", "connect-src 'self'", "object-src 'none'", "frame-ancestors 'none'",
])
DOCS_PATHS = ("/docs", "/redoc")

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
HSTS = "max-age=31536000; includeSubDomains"


def security_headers(path: str, https: bool) -> dict[str, str]:
    headers = {**BASE_HEADERS, "Content-Security-Policy": DOCS_CSP if path.startswith(DOCS_PATHS) else APP_CSP}
    if path.startswith("/api/"):
        headers["Cache-Control"] = "no-store"  # personal data: never kept by shared caches
    if https:
        headers["Strict-Transport-Security"] = HSTS
    return headers


class SecurityHeaders:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = security_headers(scope["path"], scope.get("scheme") == "https")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in extra.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimit:
    def __init__(self, app: ASGIApp, *, default_bytes: int, upload_bytes: int, upload_paths: tuple[str, ...]):
        self.app = app
        self.default_bytes = default_bytes
        self.upload_bytes = upload_bytes
        self.upload_paths = upload_paths

    def _limit(self, path: str) -> int:
        return self.upload_bytes if path.startswith(self.upload_paths) else self.default_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope["path"])
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > limit
            except ValueError:
                too_big = True
            if too_big:
                await _too_large(limit)(scope, receive, send)
                return
        received = 0
        exceeded = False
        started = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:  # chunked body without (or lying about) Content-Length
                    exceeded = True
                    return {"type": "http.disconnect"}  # stop reading; the app's own error response is replaced
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded:
                return
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
        if exceeded and not started:
            await _too_large(limit)(scope, receive, send)


def _message(limit: int) -> str:
    size = f"{limit / 2**20:.0f} MB" if limit >= 2**20 else f"{limit // 1024} KB"
    return f"Request is too large (limit {size})"


def _too_large(limit: int) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": _message(limit)})
