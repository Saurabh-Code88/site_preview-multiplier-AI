"""Site Previewer API: signup/login (JWT), capture + save website previews."""
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-change-me")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
TOKEN_HOURS = 24
BASE_DIR = Path(__file__).parent
SHOT_DIR = BASE_DIR / "screenshots"
SHOT_DIR.mkdir(exist_ok=True)

# ---------- database ----------
engine = create_engine(f"sqlite:///{BASE_DIR / 'app.db'}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | blocked | failed
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- auth ----------
bearer = HTTPBearer(auto_error=False)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UrlIn(BaseModel):
    url: str = Field(min_length=3, max_length=2000)


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user.id), "exp": exp}, SECRET_KEY, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if not creds:
        raise HTTPException(401, "Not signed in")
    try:
        uid = int(jwt.decode(creds.credentials, SECRET_KEY, algorithms=["HS256"])["sub"])
    except Exception:
        raise HTTPException(401, "Session expired. Please log in again.")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(401, "Account not found")
    return user


# ---------- url safety + screenshot ----------
def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, "Enter a valid http(s) URL.")
    # Block private/internal targets (SSRF protection) before launching a browser.
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise HTTPException(400, "Could not resolve that domain.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(400, "That address is not allowed.")
    return raw


def capture(url: str, out_path: Path) -> tuple[str, int | None, bool]:
    """Run the screenshot in a separate process (avoids Windows asyncio subprocess limits)."""
    proc = subprocess.run(
        [sys.executable, str(BASE_DIR / "capture_worker.py"), url, str(out_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        lines = [l for l in proc.stderr.strip().splitlines() if l.strip()]
        raise RuntimeError(lines[-1] if lines else "Browser failed to start")
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    return data["title"], data["status"], data["blank"]


def run_capture(site: Site) -> None:
    name = f"{uuid.uuid4().hex}.jpg"
    try:
        title, code, blank = capture(site.url, SHOT_DIR / name)
        site.title, site.screenshot = title or None, name
        if blank:
            site.status = "blocked"
            site.message = (
                "The page loaded blank. This usually means the site's bot protection "
                "stopped the automated browser."
            )
        elif code and code >= 400:
            site.status = "blocked"
            site.message = f"The site returned HTTP {code}, so the preview may show an error page."
        else:
            site.status, site.message = "ok", None
    except Exception as e:  # network error, timeout, browser not installed...
        site.status = "failed"
        site.message = f"Could not capture a preview: {(str(e) or type(e).__name__)[:200]}"


def serialize(s: Site) -> dict:
    return {
        "id": s.id,
        "url": s.url,
        "title": s.title,
        "preview_url": f"/screenshots/{s.screenshot}" if s.screenshot else None,
        "status": s.status,
        "message": s.message,
        "created_at": s.created_at.isoformat(),
    }


# ---------- app ----------
app = FastAPI(title="Site Previewer")
app.add_middleware(
    CORSMiddleware, allow_origins=[FRONTEND_ORIGIN], allow_methods=["*"], allow_headers=["*"]
)
app.mount("/screenshots", StaticFiles(directory=SHOT_DIR), name="screenshots")


@app.post("/api/auth/signup", status_code=201)
def signup(body: Credentials, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=email, password_hash=hash_pw(body.password))
    db.add(user)
    db.commit()
    return {"token": make_token(user), "email": user.email}


@app.post("/api/auth/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not check_pw(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    return {"token": make_token(user), "email": user.email}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email}


# Plain `def` routes run in FastAPI's threadpool, so the blocking capture doesn't stall the server.
@app.post("/api/sites", status_code=201)
def add_site(body: UrlIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    site = Site(user_id=user.id, url=normalize_url(body.url))
    run_capture(site)
    db.add(site)
    db.commit()
    return serialize(site)


@app.get("/api/sites")
def list_sites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Site).where(Site.user_id == user.id).order_by(Site.id.desc())).all()
    return [serialize(s) for s in rows]


@app.post("/api/sites/{site_id}/retry")
def retry_site(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if not site or site.user_id != user.id:
        raise HTTPException(404, "Not found")
    old = site.screenshot
    run_capture(site)
    if old and site.screenshot != old:
        (SHOT_DIR / old).unlink(missing_ok=True)
    db.commit()
    return serialize(site)


@app.delete("/api/sites/{site_id}", status_code=204)
def delete_site(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if not site or site.user_id != user.id:
        raise HTTPException(404, "Not found")
    if site.screenshot:
        (SHOT_DIR / site.screenshot).unlink(missing_ok=True)
    db.delete(site)
    db.commit()