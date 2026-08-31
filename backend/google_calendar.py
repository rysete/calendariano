from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "America/Sao_Paulo"

BASE_DIR = Path(__file__).resolve().parent

def _get_writable_path(env_var: str, filename: str) -> Path:
    env_val = os.getenv(env_var)
    if env_val:
        return Path(env_val)
    local_path = BASE_DIR / filename
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = local_path.parent / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return local_path
    except (OSError, PermissionError):
        data_home = Path(os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))) / "escala-web-editor"
        data_home.mkdir(parents=True, exist_ok=True)
        return data_home / filename

CREDENTIALS_FILE = _get_writable_path("GOOGLE_CREDENTIALS_FILE", "google_credential.json")
TOKEN_FILE = _get_writable_path("GOOGLE_TOKEN_FILE", "google_token.json")
OAUTH_STATE_FILE = Path(os.getenv("GOOGLE_OAUTH_STATE_FILE", "/tmp/escala_google_oauth_states.json"))

pending_states: dict[str, dict[str, str | None]] = {}


class GoogleCalendarError(RuntimeError):
    pass


def external_base_url(request: Any) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def redirect_uri(request: Any) -> str:
    return f"{external_base_url(request)}/api/google/callback"


def credentials_config() -> dict[str, Any]:
    if not CREDENTIALS_FILE.exists():
        raise GoogleCalendarError(
            f"Credenciais Google nao configuradas. Envie o OAuth client JSON em {CREDENTIALS_FILE}."
        )

    try:
        with CREDENTIALS_FILE.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
    except json.JSONDecodeError as exc:
        raise GoogleCalendarError(f"Arquivo de credenciais Google invalido: {exc}") from exc

    if "web" not in config and "installed" not in config:
        raise GoogleCalendarError("O JSON precisa ser um OAuth client do Google com chave 'web' ou 'installed'.")
    return config


def client_type(config: dict[str, Any]) -> str:
    return "web" if "web" in config else "installed"


def load_credentials() -> Credentials | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except Exception as exc:
        raise GoogleCalendarError(f"Token Google invalido. Remova {TOKEN_FILE} e conecte de novo.") from exc

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_credentials(creds)
        except RefreshError as exc:
            try:
                TOKEN_FILE.unlink()
            except FileNotFoundError:
                pass
            raise GoogleCalendarError("Token Google expirou/revogou. Conecte a conta de novo.") from exc
    return creds if creds.valid else None


def save_credentials(creds: Credentials) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")


def connect_native() -> None:
    credentials_config()
    port = int(os.getenv("GOOGLE_NATIVE_REDIRECT_PORT", "8766"))
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(
        host="127.0.0.1",
        port=port,
        authorization_prompt_message="Abra esta URL no navegador para conectar o Google Calendar: {url}",
        success_message="Google Calendar conectado. Voce ja pode voltar ao Escala Local.",
        open_browser=True,
        prompt="consent",
    )
    save_credentials(creds)


def native_status() -> dict[str, Any]:
    result: dict[str, Any] = {
        "configured": CREDENTIALS_FILE.exists(),
        "authenticated": False,
        "credentials_path": str(CREDENTIALS_FILE),
        "token_path": str(TOKEN_FILE),
        "client_type": None,
        "error": None,
    }
    if result["configured"]:
        try:
            result["client_type"] = client_type(credentials_config())
            result["authenticated"] = load_credentials() is not None
        except Exception as exc:
            result["error"] = str(exc)
    return result


def load_pending_states() -> dict[str, dict[str, str | None]]:
    if not OAUTH_STATE_FILE.exists():
        return {}
    try:
        with OAUTH_STATE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def save_pending_states() -> None:
    OAUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    OAUTH_STATE_FILE.write_text(json.dumps(pending_states), encoding="utf-8")


def calendar_service():
    creds = load_credentials()
    if not creds:
        raise GoogleCalendarError("Conta Google ainda nao conectada.")
    try:
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except GoogleAuthError as exc:
        raise GoogleCalendarError(f"Falha ao criar cliente Google Calendar: {exc}") from exc


def auth_url(request: Any) -> dict[str, str]:
    config = credentials_config()
    uri = redirect_uri(request)

    if uri.startswith("http://"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=uri)
    state = secrets.token_urlsafe(24)
    url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    pending = {"redirect_uri": uri, "code_verifier": flow.code_verifier}
    pending_states[state] = pending
    pending_states[returned_state] = pending
    save_pending_states()
    return {"auth_url": url, "redirect_uri": uri, "client_type": client_type(config)}


def finish_oauth(request: Any, code: str, state: str | None) -> None:
    if not pending_states:
        pending_states.update(load_pending_states())

    if not state or state not in pending_states:
        raise GoogleCalendarError("Estado OAuth invalido ou expirado. Gere um novo link de conexao.")

    pending = pending_states.pop(state)
    save_pending_states()
    uri = pending.get("redirect_uri")
    code_verifier = pending.get("code_verifier")
    if not uri:
        raise GoogleCalendarError("Estado OAuth sem redirect URI. Gere um novo link de conexao.")
    if not code_verifier:
        raise GoogleCalendarError("Link OAuth antigo sem code_verifier. Clique em Conectar Google de novo.")

    if uri.startswith("http://"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    flow = Flow.from_client_config(
        credentials_config(),
        scopes=SCOPES,
        state=state,
        redirect_uri=uri,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.fetch_token(code=code)
    save_credentials(flow.credentials)


def status(request: Any) -> dict[str, Any]:
    configured = CREDENTIALS_FILE.exists()
    uri = redirect_uri(request)
    result: dict[str, Any] = {
        "configured": configured,
        "authenticated": False,
        "credentials_path": str(CREDENTIALS_FILE),
        "token_path": str(TOKEN_FILE),
        "redirect_uri": uri,
        "client_type": None,
        "error": None,
    }

    if configured:
        try:
            result["client_type"] = client_type(credentials_config())
            result["authenticated"] = load_credentials() is not None
        except Exception as exc:
            result["error"] = str(exc)

    return result


def list_calendars() -> list[dict[str, Any]]:
    service = calendar_service()
    calendars: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        for item in response.get("items", []):
            access_role = item.get("accessRole")
            calendars.append(
                {
                    "id": item["id"],
                    "summary": item.get("summary", item["id"]),
                    "primary": item.get("primary", False),
                    "access_role": access_role,
                    "can_write": access_role in {"owner", "writer"},
                }
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            return calendars


def event_id(name: str, date_str: str) -> str:
    raw = f"escala:{name}:{date_str}".encode("utf-8")
    digest = base64.b32hexencode(hashlib.sha1(raw).digest()).decode("ascii").lower().rstrip("=")
    return f"escala{digest[:32]}"


def parse_local_datetime(date_str: str, time_str: str) -> datetime:
    parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    parsed_time = datetime.strptime(time_str, "%H:%M").time()
    return datetime.combine(parsed_date, parsed_time)


def event_body(data: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    name = data.get("name", "Funcionario")
    turno = data.get("turno", "N/A")
    month_name = data.get("month_name", "")
    date_str = item["date"]
    start_time = item.get("start_time", "08:00")
    end_time = item.get("end_time", "17:00")

    start_dt = parse_local_datetime(date_str, start_time)
    end_dt = parse_local_datetime(date_str, end_time)
    if end_time < start_time:
        end_dt += timedelta(days=1)

    return {
        "id": event_id(name, date_str),
        "summary": f"Trabalho - {name}",
        "description": f"Escala de trabalho\nTurno: {turno}\nFuncionario: {name}\nMes: {month_name}",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
        "transparency": "opaque",
        "colorId": "2",
        "extendedProperties": {
            "private": {
                "escala-web-editor": "1",
                "employee": name,
                "date": date_str,
            }
        },
    }


def upsert_event(service: Any, calendar_id: str, body: dict[str, Any]) -> str:
    try:
        service.events().update(calendarId=calendar_id, eventId=body["id"], body=body).execute()
        return "updated"
    except HttpError as exc:
        if exc.resp.status != 404:
            raise

    try:
        service.events().insert(calendarId=calendar_id, body=body).execute()
        return "created"
    except HttpError as exc:
        if exc.resp.status != 409:
            raise
        service.events().update(calendarId=calendar_id, eventId=body["id"], body=body).execute()
        return "updated"


def delete_event_if_exists(service: Any, calendar_id: str, event_id_value: str) -> bool:
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id_value).execute()
        return True
    except HttpError as exc:
        if exc.resp.status == 404:
            return False
        raise


def sync_escala(data: dict[str, Any], calendar_id: str = "primary") -> dict[str, int]:
    service = calendar_service()
    created = 0
    updated = 0
    deleted = 0
    skipped = 0
    name = data.get("name", "Funcionario")

    for item in data.get("escala", []):
        date_str = item.get("date")
        if not date_str:
            skipped += 1
            continue

        eid = event_id(name, date_str)
        if item.get("status") != "TRABALHO":
            if delete_event_if_exists(service, calendar_id, eid):
                deleted += 1
            continue

        action = upsert_event(service, calendar_id, event_body(data, item))
        if action == "created":
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated, "deleted": deleted, "skipped": skipped}
