"""Configuration, credential loading, and cookie persistence for nwu-mcp."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://jwgl.nwu.edu.cn/jwglxt"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "nwu-mcp"


@dataclass(frozen=True)
class Credentials:
    """User credentials for NWU Zhengfang academic system."""

    student_no: str
    password: str


def get_base_url() -> str:
    """Return the configured jwglxt base URL without trailing slash."""
    return os.environ.get("NWU_JW_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_config_dir() -> Path:
    """Return the local directory where credentials and cookies are stored."""
    raw = os.environ.get("NWU_JW_CONFIG_DIR")
    return Path(raw).expanduser() if raw else DEFAULT_CONFIG_DIR


def get_credential_path() -> Path:
    """Return the path to credential.json."""
    return get_config_dir() / "credential.json"


def get_cookie_path() -> Path:
    """Return the path to cookies.json."""
    return get_config_dir() / "cookies.json"


def load_credentials() -> Credentials:
    """Load student number and password from env vars or credential.json."""
    env_no = os.environ.get("NWU_JW_STUDENT_NO", "").strip()
    env_pwd = os.environ.get("NWU_JW_PASSWORD", "")
    if env_no and env_pwd:
        return Credentials(student_no=env_no, password=env_pwd)

    cred_path = get_credential_path()
    if not cred_path.exists():
        raise RuntimeError(
            f"未找到凭据文件 {cred_path}。请创建该文件并写入 "
            '{"studentNo": "你的学号", "password": "教务密码"}，'
            "或设置环境变量 NWU_JW_STUDENT_NO / NWU_JW_PASSWORD。"
        )

    try:
        data = json.loads(cred_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"凭据文件 {cred_path} JSON 格式无效: {exc}") from exc

    student_no = str(data.get("studentNo") or data.get("student_no") or "").strip()
    password = str(data.get("password") or "")
    if not student_no or not password:
        raise RuntimeError(
            f"凭据文件 {cred_path} 缺少 studentNo 或 password 字段。"
        )
    return Credentials(student_no=student_no, password=password)


def save_cookies(cookies: dict[str, str], cookie_path: Path | None = None) -> None:
    """Persist session cookies to disk."""
    path = cookie_path or get_cookie_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cookies(cookie_path: Path | None = None) -> dict[str, str]:
    """Load persisted session cookies from disk if present and valid."""
    path = cookie_path or get_cookie_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None}
