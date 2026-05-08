from __future__ import annotations

"""Local SQLite-backed auth and role-policy store for the demo web app."""

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Any

from mini_rag.ingestion.kb_config import normalize_kb_ids
from mini_rag.security.permissions import RolePolicy, TOOL_PERMISSIONS, VALID_ROLES, default_role_policy, normalize_role
from mini_rag.utils import ensure_dir


DEMO_USERS: tuple[tuple[str, str, str], ...] = (
    ("admin", "admin123", "admin"),
    ("employee", "employee123", "employee"),
    ("finance", "finance123", "finance"),
    ("hr", "hr123", "hr"),
    ("it", "it123", "it"),
    ("guest", "guest123", "guest"),
)

PBKDF2_ITERATIONS = 120_000


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str
    enabled: bool = True


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    user: AuthUser


class SQLiteAuthStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        ensure_dir(self.db_path.parent)
        self._init_db()
        self._seed_defaults()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS role_policies (
                    role TEXT PRIMARY KEY,
                    allowed_kbs_json TEXT NOT NULL,
                    allowed_tools_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username)")

    def _seed_defaults(self) -> None:
        now = time.time()
        with self._connect() as conn:
            for role in sorted(VALID_ROLES):
                policy = default_role_policy(role)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO role_policies(role, allowed_kbs_json, allowed_tools_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        role,
                        json.dumps(policy.allowed_kbs, ensure_ascii=False),
                        json.dumps(policy.allowed_tools, ensure_ascii=False),
                        now,
                    ),
                )
            for username, password, role in DEMO_USERS:
                salt, password_hash = hash_password(password)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users(username, password_hash, salt, role, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (username, password_hash, salt, normalize_role(role), now, now),
                )

    def authenticate_password(self, username: str, password: str) -> AuthUser | None:
        username = normalize_username(username)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username, password_hash, salt, role, enabled FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if not row or not int(row["enabled"]):
            return None
        expected_hash = str(row["password_hash"])
        candidate_hash = derive_password_hash(password, str(row["salt"]))
        if not hmac.compare_digest(expected_hash, candidate_hash):
            return None
        return row_to_user(row)

    def login(self, username: str, password: str) -> LoginResult | None:
        user = self.authenticate_password(username, password)
        if user is None:
            return None
        token = secrets.token_urlsafe(32)
        token_hash = hash_token(token)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions(token_hash, username, created_at, revoked) VALUES (?, ?, ?, 0)",
                (token_hash, user.username, time.time()),
            )
        return LoginResult(access_token=token, user=user)

    def logout(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sessions SET revoked = 1 WHERE token_hash = ?", (hash_token(token),))

    def authenticate_token(self, token: str) -> AuthUser | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.username, u.role, u.enabled
                FROM sessions s
                JOIN users u ON u.username = s.username
                WHERE s.token_hash = ? AND s.revoked = 0
                """,
                (hash_token(token),),
            ).fetchone()
        if not row or not int(row["enabled"]):
            return None
        return row_to_user(row)

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT username, role, enabled, created_at, updated_at FROM users ORDER BY username"
            ).fetchall()
        return [
            {
                "username": row["username"],
                "role": row["role"],
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def create_user(self, username: str, password: str, role: str, enabled: bool = True) -> AuthUser:
        username = normalize_username(username)
        role = normalize_role(role)
        if not username:
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")
        salt, password_hash = hash_password(password)
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(username, password_hash, salt, role, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (username, password_hash, salt, role, int(enabled), now, now),
            )
        return AuthUser(username=username, role=role, enabled=enabled)

    def update_user(
        self,
        username: str,
        role: str | None = None,
        enabled: bool | None = None,
        password: str | None = None,
    ) -> AuthUser | None:
        username = normalize_username(username)
        fields: list[str] = []
        values: list[Any] = []
        if role is not None:
            fields.append("role = ?")
            values.append(normalize_role(role))
        if enabled is not None:
            fields.append("enabled = ?")
            values.append(int(enabled))
        if password:
            salt, password_hash = hash_password(password)
            fields.extend(["password_hash = ?", "salt = ?"])
            values.extend([password_hash, salt])
        if not fields:
            return self.get_user(username)
        fields.append("updated_at = ?")
        values.append(time.time())
        values.append(username)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE username = ?", values)
            if cur.rowcount == 0:
                return None
        return self.get_user(username)

    def get_user(self, username: str) -> AuthUser | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username, role, enabled FROM users WHERE username = ?",
                (normalize_username(username),),
            ).fetchone()
        return row_to_user(row) if row else None

    def list_role_policies(self) -> dict[str, RolePolicy]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, allowed_kbs_json, allowed_tools_json FROM role_policies ORDER BY role"
            ).fetchall()
        return {str(row["role"]): row_to_policy(row) for row in rows}

    def update_role_policy(self, role: str, allowed_kbs: list[str], allowed_tools: list[str]) -> RolePolicy:
        role = normalize_role(role)
        if role not in VALID_ROLES:
            raise ValueError(f"unknown role: {role}")
        valid_tools = set(TOOL_PERMISSIONS)
        normalized_tools = sorted({str(tool) for tool in allowed_tools if str(tool) in valid_tools})
        policy = RolePolicy(role=role, allowed_kbs=normalize_kb_ids(allowed_kbs), allowed_tools=normalized_tools)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO role_policies(role, allowed_kbs_json, allowed_tools_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(role) DO UPDATE SET
                    allowed_kbs_json = excluded.allowed_kbs_json,
                    allowed_tools_json = excluded.allowed_tools_json,
                    updated_at = excluded.updated_at
                """,
                (
                    role,
                    json.dumps(policy.allowed_kbs, ensure_ascii=False),
                    json.dumps(policy.allowed_tools, ensure_ascii=False),
                    time.time(),
                ),
            )
        return policy


def normalize_username(username: str | None) -> str:
    return str(username or "").strip().lower()


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, derive_password_hash(password, salt)


def derive_password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()


def hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def row_to_user(row: sqlite3.Row) -> AuthUser:
    return AuthUser(username=str(row["username"]), role=normalize_role(row["role"]), enabled=bool(row["enabled"]))


def row_to_policy(row: sqlite3.Row) -> RolePolicy:
    return RolePolicy(
        role=normalize_role(row["role"]),
        allowed_kbs=normalize_kb_ids(json.loads(row["allowed_kbs_json"] or "[]")),
        allowed_tools=[str(item) for item in json.loads(row["allowed_tools_json"] or "[]")],
    )
