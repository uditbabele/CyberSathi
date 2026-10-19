
from datetime import datetime, timedelta, timezone
import hashlib, hmac, base64, json, os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .db import get_db
from .models import User
from .config import JWT_SECRET, JWT_EXPIRE_MINUTES, ADMIN_USERNAME, ADMIN_PASSWORD

bearer = HTTPBearer(auto_error=False)

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def password_hash(password: str, salt: str = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, expected = encoded.split("$", 2)
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def create_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    header = _b64(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",",":")).encode())
    payload = _b64(json.dumps({"sub":username,"role":role,"iat":int(now.timestamp()),
        "exp":int((now+timedelta(minutes=JWT_EXPIRE_MINUTES)).timestamp())}, separators=(",",":")).encode())
    signing = f"{header}.{payload}".encode()
    signature = _b64(hmac.new(JWT_SECRET.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"

def decode_token(token: str):
    try:
        header, payload, signature = token.split(".")
        signing = f"{header}.{payload}".encode()
        expected = _b64(hmac.new(JWT_SECRET.encode(), signing, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): raise ValueError("signature")
        data = json.loads(_unb64(payload))
        if int(data["exp"]) < int(datetime.now(timezone.utc).timestamp()): raise ValueError("expired")
        return data
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired access token.")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Sign in to access this endpoint.")
    payload = decode_token(credentials.credentials)
    user = db.query(User).filter(User.username == payload.get("sub"), User.active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User is inactive or no longer exists.")
    return user

def require_role(*roles):
    def checker(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Your role is not allowed to perform this action.")
        return user
    return checker

def seed_admin(db: Session):
    user = db.query(User).filter(User.username == ADMIN_USERNAME).first()
    if not user:
        db.add(User(username=ADMIN_USERNAME, password_hash=password_hash(ADMIN_PASSWORD), role="admin", active=True))
        db.commit()
