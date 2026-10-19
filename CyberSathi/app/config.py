
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./traceweave.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-this-secret-before-deployment")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "TraceWeaveDemo2026!")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
