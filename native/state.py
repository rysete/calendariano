from __future__ import annotations

import copy
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from backend.bridge import EscalaBridge
from backend import google_calendar


@dataclass
class NativeState:
    name_column: int = 0
    file_path: str | None = None
    bridge: EscalaBridge | None = None
    months: list[dict[str, Any]] = field(default_factory=list)
    employees: list[dict[str, Any]] = field(default_factory=list)
    turnos: dict[str, dict[str, str]] = field(default_factory=dict)
    selected_month_id: str | None = None
    selected_employee_id: int | None = None
    escala: dict[str, Any] | None = None
    google_status: dict[str, Any] = field(default_factory=dict)
    google_calendars: list[dict[str, Any]] = field(default_factory=list)
    selected_google_calendar_id: str = "primary"
    status: str = "Carregue uma planilha Excel para comecar."
    error: str | None = None
    version: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name_column": self.name_column,
                "file_path": self.file_path,
                "months": copy.deepcopy(self.months),
                "employees": copy.deepcopy(self.employees),
                "turnos": copy.deepcopy(self.turnos),
                "selected_month_id": self.selected_month_id,
                "selected_employee_id": self.selected_employee_id,
                "escala": copy.deepcopy(self.escala),
                "google_status": copy.deepcopy(self.google_status),
                "google_calendars": copy.deepcopy(self.google_calendars),
                "selected_google_calendar_id": self.selected_google_calendar_id,
                "status": self.status,
                "error": self.error,
                "version": self.version,
            }

    def load_file(self, path: str, col_nome: int | None = None) -> dict[str, Any]:
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        if not path.lower().endswith((".xlsx", ".xls")):
            raise ValueError("Escolha uma planilha Excel (.xlsx ou .xls).")

        column = self.name_column if col_nome is None else int(col_nome)
        bridge = EscalaBridge(path, col_nome=column)
        months = bridge.get_months()

        with self._lock:
            self.name_column = column
            self.file_path = path
            self.bridge = bridge
            self.months = months
            self.turnos = bridge.get_turnos()
            self.selected_month_id = months[0]["id"] if months else None
            self.selected_employee_id = None
            self.employees = []
            self.escala = None
            self.error = None
            self.status = f"Planilha carregada: {os.path.basename(path)}"
            self.version += 1

        if months:
            self.select_month(months[0]["id"])

        return {"months": months, "status": self.status, "version": self.version}

    def set_name_column(self, col_nome: int) -> None:
        with self._lock:
            self.name_column = int(col_nome)
            self.version += 1

    def select_month(self, month_id: str) -> None:
        with self._lock:
            bridge = self.bridge
        if bridge is None:
            return

        employees = bridge.get_employees(month_id)
        with self._lock:
            self.selected_month_id = month_id
            self.employees = employees
            self.selected_employee_id = employees[0]["id"] if employees else None
            self.escala = None
            self.error = None
            self.version += 1

        if employees:
            self.select_employee(int(employees[0]["id"]))

    def select_employee(self, employee_id: int) -> None:
        with self._lock:
            bridge = self.bridge
            month_id = self.selected_month_id
        if bridge is None or month_id is None:
            return

        escala = bridge.get_escala(month_id, int(employee_id))
        with self._lock:
            self.selected_employee_id = int(employee_id)
            self.escala = escala
            self.error = None
            self.version += 1

    def update_day(self, index: int, **changes: Any) -> None:
        with self._lock:
            if not self.escala:
                return
            days = self.escala.get("escala", [])
            if index < 0 or index >= len(days):
                return
            days[index].update(changes)
            if ("start_time" in changes or "end_time" in changes or "status" in changes) and "colegas" not in changes:
                if self.bridge and self.selected_month_id:
                    days[index]["colegas"] = self.bridge.get_colegas(
                        self.selected_month_id,
                        days[index]["date"],
                        days[index].get("start_time", "08:00"),
                        days[index].get("end_time", "17:00"),
                        self.escala.get("name", "")
                    )
            self.version += 1

    def set_turno(self, turno: str) -> None:
        turno = turno.strip() or "08x17"
        start_time = ""
        end_time = ""
        with self._lock:
            if not self.escala:
                return
            if turno in self.turnos:
                start_time = self.turnos[turno].get("inicio", "")
                end_time = self.turnos[turno].get("fim", "")
            elif "x" in turno.lower():
                separator = "x" if "x" in turno else "X"
                start_raw, _, end_raw = turno.partition(separator)
                if start_raw.isdigit() and end_raw.isdigit():
                    start_time = f"{int(start_raw):02d}:00"
                    end_time = f"{int(end_raw):02d}:00"

            self.escala["turno"] = turno
            if start_time and end_time:
                for day in self.escala.get("escala", []):
                    if day.get("status") == "TRABALHO":
                        day["start_time"] = start_time
                        day["end_time"] = end_time
                        if self.bridge and self.selected_month_id:
                            day["colegas"] = self.bridge.get_colegas(
                                self.selected_month_id,
                                day["date"],
                                start_time,
                                end_time,
                                self.escala.get("name", "")
                            )
            self.version += 1

    def set_status(self, message: str) -> None:
        with self._lock:
            self.status = message
            self.error = None
            self.version += 1

    def set_error(self, message: str) -> None:
        with self._lock:
            self.error = message
            self.status = message
            self.version += 1

    def refresh_google(self) -> dict[str, Any]:
        status = google_calendar.native_status()
        calendars: list[dict[str, Any]] = []
        selected = self.selected_google_calendar_id
        if status.get("authenticated"):
            calendars = [item for item in google_calendar.list_calendars() if item.get("can_write") is not False]
            existing = {item["id"] for item in calendars}
            if selected not in existing:
                primary = next((item for item in calendars if item.get("primary")), None)
                selected = (primary or calendars[0])["id"] if calendars else "primary"

        with self._lock:
            self.google_status = status
            self.google_calendars = calendars
            self.selected_google_calendar_id = selected
            self.error = status.get("error")
            self.version += 1
        return status

    def save_google_credentials(self, path: str) -> None:
        path = os.path.abspath(os.path.expanduser(path))
        with open(path, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if "web" not in parsed and "installed" not in parsed:
            raise ValueError("O JSON precisa conter a chave 'web' ou 'installed'.")
        google_calendar.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        google_calendar.CREDENTIALS_FILE.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        self.refresh_google()

    def connect_google(self) -> None:
        google_calendar.connect_native()
        self.refresh_google()

    def select_google_calendar(self, calendar_id: str) -> None:
        with self._lock:
            self.selected_google_calendar_id = calendar_id or "primary"
            self.version += 1

    def sync_google(self) -> dict[str, int]:
        with self._lock:
            data = copy.deepcopy(self.escala)
            calendar_id = self.selected_google_calendar_id or "primary"
        if not data:
            raise ValueError("Nenhuma escala selecionada.")
        result = google_calendar.sync_escala(data, calendar_id=calendar_id)
        with self._lock:
            self.status = (
                f"Google sincronizado: {result.get('created', 0)} criados, "
                f"{result.get('updated', 0)} atualizados, "
                f"{result.get('deleted', 0)} removidos."
            )
            self.error = None
            self.version += 1
        return result

    def export_csv(self) -> str:
        with self._lock:
            bridge = self.bridge or EscalaBridge()
            data = copy.deepcopy(self.escala)
        if not data:
            raise ValueError("Nenhuma escala selecionada.")
        return bridge.generate_csv_content(data)

    def export_ics(self) -> bytes:
        with self._lock:
            bridge = self.bridge or EscalaBridge()
            data = copy.deepcopy(self.escala)
        if not data:
            raise ValueError("Nenhuma escala selecionada.")
        content = bridge.generate_ics_content(data)
        return content if isinstance(content, bytes) else content.encode("utf-8")


state = NativeState()
