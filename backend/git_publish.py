from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .bridge import EscalaBridge

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_REPO_DIR = os.path.expanduser("~/gemini/escala-web-editor")
DEFAULT_PAGES_BASE = "https://rysete.github.io/calendariano"
DEFAULT_EMPLOYEE = "RYAN"


def _get_settings_file() -> Path:
    env_val = os.getenv("ESCALA_SETTINGS_FILE")
    if env_val:
        return Path(env_val)
    data_home = Path(os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))) / "escala-web-editor"
    try:
        data_home.mkdir(parents=True, exist_ok=True)
        return data_home / "settings.json"
    except (OSError, PermissionError):
        return Path("/tmp/escala_settings.json")


SETTINGS_FILE = _get_settings_file()


def load_settings() -> dict[str, Any]:
    defaults = {
        "repo_dir": os.getenv("ESCALA_REPO", DEFAULT_REPO_DIR),
        "pages_base": os.getenv("ESCALA_PAGES_BASE", DEFAULT_PAGES_BASE),
        "default_employee": os.getenv("ESCALA_DEFAULT_EMPLOYEE", DEFAULT_EMPLOYEE),
    }
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update({k: v for k, v in data.items() if v is not None})
    except Exception:
        pass
    return defaults


def save_settings(**updates: Any) -> dict[str, Any]:
    current = load_settings()
    for k, v in updates.items():
        if v is not None:
            current[k] = v
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def is_flatpak() -> bool:
    return os.path.exists("/.flatpak-info")


def run_git_cmd(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    if is_flatpak() and shutil.which("flatpak-spawn"):
        cmd = ["flatpak-spawn", "--host", f"--directory={cwd}", *args]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0 or "org.freedesktop.Flatpak" not in (res.stderr or ""):
            return res
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)


def safe_employee_slug(name: str) -> str:
    slug = "".join(c if c.isalnum() else "_" for c in (name or "escala").lower()).strip("_")
    return slug or "escala"


def derive_pages_base(remote_url: str, fallback: str = DEFAULT_PAGES_BASE) -> str:
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", (remote_url or "").strip())
    if m:
        user, repo = m.group(1), m.group(2)
        return f"https://{user}.github.io/{repo}"
    return fallback


def repo_status(repo_dir: str | None = None, pages_base: str | None = None, employee_name: str | None = None) -> dict[str, Any]:
    cfg = load_settings()
    resolved_repo = os.path.abspath(os.path.expanduser(repo_dir or cfg.get("repo_dir") or DEFAULT_REPO_DIR))
    resolved_pages = (pages_base or cfg.get("pages_base") or DEFAULT_PAGES_BASE).rstrip("/")
    emp_slug = safe_employee_slug(employee_name or cfg.get("default_employee") or "ryan")

    git_dir = os.path.join(resolved_repo, ".git")
    cal_dir = os.path.join(resolved_repo, "backend", "calendars")
    docs_dir = os.path.join(resolved_repo, "docs")
    valid = os.path.isdir(git_dir) and os.path.isdir(cal_dir)

    branch = ""
    last_commit = ""
    remote_url = ""
    error = None

    if valid:
        try:
            r_branch = run_git_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=resolved_repo)
            if r_branch.returncode == 0:
                branch = r_branch.stdout.strip()
            r_commit = run_git_cmd(["git", "log", "-1", "--oneline"], cwd=resolved_repo)
            if r_commit.returncode == 0:
                last_commit = r_commit.stdout.strip()
            r_remote = run_git_cmd(["git", "remote", "get-url", "origin"], cwd=resolved_repo)
            if r_remote.returncode == 0:
                remote_url = r_remote.stdout.strip()
                if not pages_base and not cfg.get("pages_base"):
                    resolved_pages = derive_pages_base(remote_url, resolved_pages)
        except Exception as exc:
            error = str(exc)
    else:
        error = f"Repositório não encontrado em {resolved_repo}"

    main_ics_url = f"{resolved_pages}/calendario.ics"
    emp_ics_url = f"{resolved_pages}/{emp_slug}.ics"

    return {
        "valid": valid,
        "repo_dir": resolved_repo,
        "calendars_dir": cal_dir,
        "docs_dir": docs_dir,
        "branch": branch or "master",
        "last_commit": last_commit,
        "remote_url": remote_url,
        "pages_base": resolved_pages,
        "main_ics_url": main_ics_url,
        "main_webcal_url": main_ics_url.replace("https://", "webcal://").replace("http://", "webcal://"),
        "employee_ics_url": emp_ics_url,
        "employee_webcal_url": emp_ics_url.replace("https://", "webcal://").replace("http://", "webcal://"),
        "default_employee": cfg.get("default_employee", DEFAULT_EMPLOYEE),
        "error": error,
    }


def regenerate_repo_ics(repo_dir: str, preferred_json: str | None = None) -> list[str]:
    cal_dir = os.path.join(repo_dir, "backend", "calendars")
    docs_dir = os.path.join(repo_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)

    if not os.path.isdir(cal_dir):
        return []

    json_files = sorted(f for f in os.listdir(cal_dir) if f.endswith(".json"))
    if not json_files:
        return []

    if preferred_json and preferred_json in json_files:
        principal = preferred_json
    elif "calendario.json" in json_files:
        principal = "calendario.json"
    else:
        principal = max(json_files, key=lambda f: os.path.getmtime(os.path.join(cal_dir, f)))

    bridge = EscalaBridge.__new__(EscalaBridge)
    written: list[str] = []

    for filename in json_files:
        json_path = os.path.join(cal_dir, filename)
        ics_filename = filename[:-5] + ".ics"
        ics_path = os.path.join(docs_dir, ics_filename)

        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        ics_bytes = bridge.generate_ics_content(data)
        if isinstance(ics_bytes, str):
            ics_bytes = ics_bytes.encode("utf-8")

        with open(ics_path, "wb") as fh:
            fh.write(ics_bytes)
        written.append(ics_path)

        if filename == principal:
            main_ics_path = os.path.join(docs_dir, "calendario.ics")
            with open(main_ics_path, "wb") as fh:
                fh.write(ics_bytes)
            written.append(main_ics_path)

    return written


def publish_escala(
    data: dict[str, Any],
    repo_dir: str | None = None,
    pages_base: str | None = None,
    push: bool = True,
) -> dict[str, Any]:
    if not data or not data.get("escala"):
        raise ValueError("Nenhuma escala selecionada para publicar.")

    info = repo_status(repo_dir=repo_dir, pages_base=pages_base, employee_name=data.get("name"))
    if not info["valid"]:
        raise RuntimeError(info.get("error") or f"Repositório inválido: {info['repo_dir']}")

    resolved_repo = info["repo_dir"]
    cal_dir = info["calendars_dir"]
    os.makedirs(cal_dir, exist_ok=True)

    emp_name = data.get("name", "Funcionario")
    safe_name = safe_employee_slug(emp_name)
    json_filename = f"{safe_name}.json"
    json_path = os.path.join(cal_dir, json_filename)

    if push:
        # Sincroniza com o remoto antes de gerar para evitar conflito em docs/*.ics
        run_git_cmd(["git", "fetch", "origin", "--quiet"], cwd=resolved_repo)
        run_git_cmd(["git", "checkout", "--", "docs/calendario.ics", f"docs/{safe_name}.ics"], cwd=resolved_repo)
        behind_res = run_git_cmd(["git", "rev-list", "--count", "HEAD..origin/master"], cwd=resolved_repo)
        if behind_res.returncode == 0 and behind_res.stdout.strip().isdigit():
            if int(behind_res.stdout.strip()) > 0:
                merge_res = run_git_cmd(["git", "merge", "--no-edit", "origin/master"], cwd=resolved_repo)
                if merge_res.returncode != 0:
                    raise RuntimeError(f"Conflito ao atualizar origin/master: {merge_res.stderr.strip()}")

    days = sorted(data.get("escala", []), key=lambda item: item.get("date", ""))
    payload = {
        "name": emp_name,
        "turno": data.get("turno", "N/A"),
        "month_name": data.get("month_name", ""),
        "escala": days,
    }

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    regenerate_repo_ics(resolved_repo, preferred_json=json_filename)

    work_days = sum(1 for d in days if d.get("status") == "TRABALHO")

    if not push:
        updated = repo_status(repo_dir=resolved_repo, pages_base=pages_base, employee_name=emp_name)
        return {
            "published": True,
            "pushed": False,
            "unchanged": False,
            "commit": updated["last_commit"],
            "json_path": json_path,
            "work_days": work_days,
            "main_ics_url": updated["main_ics_url"],
            "employee_ics_url": updated["employee_ics_url"],
            "message": f"ICS e JSON gerados localmente ({work_days} dias de trabalho). Sem push.",
        }

    add_res = run_git_cmd(
        ["git", "add", f"backend/calendars/{json_filename}", "docs/calendario.ics", f"docs/{safe_name}.ics"],
        cwd=resolved_repo,
    )
    if add_res.returncode != 0:
        raise RuntimeError(f"Erro no git add: {add_res.stderr.strip()}")

    diff_res = run_git_cmd(["git", "diff", "--cached", "--name-only"], cwd=resolved_repo)
    staged = [line.strip() for line in (diff_res.stdout or "").splitlines() if line.strip()]

    if not staged:
        updated = repo_status(repo_dir=resolved_repo, pages_base=pages_base, employee_name=emp_name)
        return {
            "published": True,
            "pushed": False,
            "unchanged": True,
            "commit": updated["last_commit"],
            "json_path": json_path,
            "work_days": work_days,
            "main_ics_url": updated["main_ics_url"],
            "employee_ics_url": updated["employee_ics_url"],
            "message": f"Agenda já está em dia no GitHub ({work_days} dias de trabalho).",
        }

    commit_msg = f"update: escala {safe_name}"
    commit_res = run_git_cmd(["git", "commit", "-m", commit_msg], cwd=resolved_repo)
    if commit_res.returncode != 0:
        raise RuntimeError(f"Erro no git commit: {commit_res.stderr.strip() or commit_res.stdout.strip()}")

    branch = info.get("branch") or "master"
    push_res = run_git_cmd(["git", "push", "origin", branch], cwd=resolved_repo)
    if push_res.returncode != 0:
        raise RuntimeError(f"Erro no git push: {push_res.stderr.strip() or push_res.stdout.strip()}")

    updated = repo_status(repo_dir=resolved_repo, pages_base=pages_base, employee_name=emp_name)
    return {
        "published": True,
        "pushed": True,
        "unchanged": False,
        "commit": updated["last_commit"],
        "json_path": json_path,
        "work_days": work_days,
        "main_ics_url": updated["main_ics_url"],
        "employee_ics_url": updated["employee_ics_url"],
        "message": f"Publicado no GitHub ({updated['last_commit']}) — {work_days} dias de trabalho.",
    }
