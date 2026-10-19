"""Production-hardening helpers: strict config validation and request size guard."""
import os, secrets
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class MaxRequestBodyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes=10_500_000):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    raise HTTPException(status_code=413, detail="Request body exceeds configured size limit.")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Content-Length header.")
        return await call_next(request)

def validate_production_config():
    if os.getenv("ENVIRONMENT", "development").lower() != "production":
        return
    secret = os.getenv("JWT_SECRET", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if len(secret) < 32 or secret in {"dev-only-change-this-secret-before-deployment","local-development-secret-change-before-deployment"}:
        raise RuntimeError("Production requires JWT_SECRET with at least 32 characters from a secrets manager.")
    if len(admin_password) < 16 or admin_password == "TraceWeaveDemo2026!":
        raise RuntimeError("Production requires a unique ADMIN_PASSWORD of at least 16 characters.")
    if os.getenv("DATABASE_URL","").startswith("sqlite"):
        raise RuntimeError("Production must use PostgreSQL or another approved server database.")
