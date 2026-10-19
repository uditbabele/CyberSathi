import os
import pytest
from app.security_hardening import validate_production_config

def test_production_config_rejects_demo_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT","production")
    monkeypatch.setenv("JWT_SECRET","dev-only-change-this-secret-before-deployment")
    monkeypatch.setenv("ADMIN_PASSWORD","TraceWeaveDemo2026!")
    monkeypatch.setenv("DATABASE_URL","sqlite:///./traceweave.db")
    with pytest.raises(RuntimeError):
        validate_production_config()

def test_development_config_does_not_raise(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT","development")
    validate_production_config()
