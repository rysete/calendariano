from __future__ import annotations

import os
import sys
import threading
import traceback
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from native.state import state


WEEKDAYS = {
    "Monday": "Seg",
    "Tuesday": "Ter",
    "Wednesday": "Qua",
    "Thursday": "Qui",
    "Friday": "Sex",
    "Saturday": "Sab",
    "Sunday": "Dom",
}


CSS = """
.app-view {
    padding: 0;
}
.drop-active {
    border: 3px dashed #3584e4;
    background-color: rgba(53, 132, 228, 0.10);
}
.drop-overlay-label {
    font-size: 1.35em;
    font-weight: bold;
    color: #3584e4;
}
.path-display {
    background-color: rgba(127, 127, 127, 0.12);
    border-radius: 8px;
    padding: 8px 12px;
}
.section-title {
    font-weight: bold;
    font-size: 1.05em;
}
.sidebar {
    padding: 14px;
    border-right: 1px solid rgba(127, 127, 127, 0.20);
}
.editor-panel {
    padding: 16px;
}
.sidebar-section {
    margin-top: 12px;
}
.month-row {
    border-radius: 8px;
    padding: 8px;
}
.month-button {
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 48px;
}
.month-button.selected {
    background-color: alpha(#3584e4, 0.18);
}
.month-carousel-container {
    background-color: alpha(@window_fg_color, 0.03);
    border-bottom: 1px solid alpha(@window_fg_color, 0.1);
    padding: 20px 0;
    min-height: 120px;
}
.month-page {
    padding: 0;
    border-radius: 12px;
    min-width: 240px;
}
.month-page-content {
    padding: 16px 32px;
}
.month-page:hover {
    background-color: alpha(@accent_color, 0.08);
}
.month-page.selected {
    border: 2px solid @accent_color;
    background-color: alpha(@accent_color, 0.12);
}
.month-row.selected,
.employee-row.selected {
    background-color: alpha(#3584e4, 0.18);
}
.employee-row {
    border-radius: 8px;
    padding: 8px;
}
.employee-name {
    font-weight: bold;
}
.pill {
    border-radius: 999px;
    background-color: rgba(127, 127, 127, 0.16);
    padding: 2px 8px;
    font-size: 0.85em;
}
.day-card {
    border-radius: 8px;
    padding: 10px;
    border: 1px solid rgba(127, 127, 127, 0.25);
}
.day-card.work {
    background-color: alpha(#2ec27e, 0.10);
    border-color: alpha(#2ec27e, 0.55);
}
.day-card.off {
    background-color: alpha(#f6d32d, 0.16);
    border-color: alpha(#f6d32d, 0.65);
}
.day-number {
    font-size: 1.35em;
    font-weight: bold;
}
.muted {
    opacity: 0.70;
}
.error {
    color: #c01c28;
}
.toolbar-row {
    padding: 8px 12px;
    border-bottom: 1px solid rgba(127, 127, 127, 0.20);
}
"""


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def clear_children(widget: Gtk.Widget) -> None:
    child = widget.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        widget.remove(child)
        child = next_child


def safe_filename(value: str, fallback: str) -> str:
    name = "".join(char if char.isalnum() or char in "-_" else "_" for char in value).strip("_")
    return name or fallback


class FileChooserWidget(Gtk.Box):
    def __init__(self, title: str, filter_name: str, patterns: list[str]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.file_path: str | None = None
        self.filter_name = filter_name
        self.patterns = patterns

        label = Gtk.Label(label=f"<b>{title}</b>", xalign=0, use_markup=True)
        self.append(label)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(row)

        self.path_label = Gtk.Label(label="Nenhum arquivo selecionado", xalign=0, hexpand=True)
        self.path_label.set_ellipsize(Pango.EllipsizeMode.START)
        self.path_label.add_css_class("path-display")
        row.append(self.path_label)

        button = Gtk.Button(label="Selecionar")
        button.connect("clicked", self.on_select_clicked)
        row.append(button)

    def on_select_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Selecione a planilha")

        file_filter = Gtk.FileFilter.new()
        file_filter.set_name(self.filter_name)
        for pattern in self.patterns:
            file_filter.add_pattern(pattern)

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self.on_file_selected)

    def on_file_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if file:
            self.set_file_path(file.get_path())

    def set_file_path(self, path: str | None) -> None:
        self.file_path = path
        if path:
            self.path_label.set_label(f"Arquivo: {os.path.basename(path)}")
        else:
            self.path_label.set_label("Nenhum arquivo selecionado")

    def get_file_path(self) -> str | None:
        return self.file_path


class EscalaView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("app-view")

        self._last_version = -1
        self._loading = False
        self._google_busy = False
        self._calendar_ids: list[str] = []
        self._last_month_ids: list[str] = []
        self._carousel_pages: dict[str, Gtk.Widget] = {}
        self._blocking_carousel_signal = False

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.content_box.set_hexpand(True)
        self.content_box.set_vexpand(True)

        self.drop_overlay = Gtk.Overlay()
        self.drop_overlay.set_child(self.content_box)
        self.append(self.drop_overlay)

        overlay_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        overlay_box.set_halign(Gtk.Align.CENTER)
        overlay_box.set_valign(Gtk.Align.CENTER)
        overlay_label = Gtk.Label(label="Solte a planilha Excel aqui")
        overlay_label.add_css_class("drop-overlay-label")
        overlay_box.append(overlay_label)
        overlay_box.set_visible(False)
        self.overlay_box = overlay_box
        self.drop_overlay.add_overlay(overlay_box)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        toolbar.add_css_class("toolbar-row")
        toolbar.set_hexpand(True)
        self.content_box.append(toolbar)

        title = Gtk.Label(xalign=0, hexpand=True)
        title.set_markup("<b>Escala Local</b>")
        toolbar.append(title)

        self.column_input = Gtk.SpinButton.new_with_range(0, 50, 1)
        self.column_input.set_value(state.snapshot()["name_column"])
        self.column_input.connect("value-changed", self.on_column_changed)
        self.column_input.set_tooltip_text("Coluna do nome: 0=A, 1=B...")
        toolbar.append(Gtk.Label(label="Coluna:"))
        toolbar.append(self.column_input)

        self.load_button = Gtk.Button(label="Carregar")
        self.load_button.connect("clicked", self.on_load_clicked)
        toolbar.append(self.load_button)

        self.csv_button = Gtk.Button(label="Salvar CSV")
        self.csv_button.connect("clicked", lambda _button: self.save_export("csv"))
        toolbar.append(self.csv_button)

        self.ics_button = Gtk.Button(label="Salvar ICS")
        self.ics_button.connect("clicked", lambda _button: self.save_export("ics"))
        toolbar.append(self.ics_button)

        self.calendar_combo = Gtk.ComboBoxText()
        self.calendar_combo.set_tooltip_text("Agenda Google destino")
        self.calendar_combo.connect("changed", self.on_google_calendar_changed)
        toolbar.append(self.calendar_combo)

        self.google_sync_button = Gtk.Button(label="Sync Google")
        self.google_sync_button.connect("clicked", self.on_google_sync_clicked)
        toolbar.append(self.google_sync_button)

        self.settings_button = Gtk.Button(label="Configuracoes")
        self.settings_button.connect("clicked", self.on_settings_clicked)
        toolbar.append(self.settings_button)

        self.spinner = Gtk.Spinner()
        toolbar.append(self.spinner)

        workspace = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        workspace.set_wide_handle(True)
        workspace.set_resize_start_child(False)
        workspace.set_shrink_start_child(False)
        workspace.set_vexpand(True)
        self.content_box.append(workspace)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(320, -1)
        workspace.set_start_child(sidebar)

        self.chooser = FileChooserWidget("Planilha Excel:", "Planilhas Excel", ["*.xlsx", "*.xls"])
        sidebar.append(self.chooser)

        self.status_label = Gtk.Label(xalign=0, wrap=True)
        self.status_label.add_css_class("muted")
        sidebar.append(self.status_label)

        self.google_status_label = Gtk.Label(xalign=0, wrap=True)
        self.google_status_label.add_css_class("muted")
        sidebar.append(self.section("Google Agenda", self.google_status_label))

        google_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.google_calendar_sidebar = Gtk.ComboBoxText()
        self.google_calendar_sidebar.connect("changed", self.on_google_calendar_changed)
        google_controls.append(self.google_calendar_sidebar)

        google_button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.google_sync_sidebar_button = Gtk.Button(label="Sync Google")
        self.google_sync_sidebar_button.connect("clicked", self.on_google_sync_clicked)
        google_button_row.append(self.google_sync_sidebar_button)

        self.settings_button_sidebar = Gtk.Button(label="Configuracoes")
        self.settings_button_sidebar.connect("clicked", self.on_settings_clicked)
        google_button_row.append(self.settings_button_sidebar)
        google_controls.append(google_button_row)
        sidebar.append(google_controls)

        self.employee_list = Gtk.ListBox()
        self.employee_list.set_selection_mode(Gtk.SelectionMode.NONE)
        employee_scroll = Gtk.ScrolledWindow()
        employee_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        employee_scroll.set_child(self.employee_list)
        employee_scroll.set_vexpand(True)
        sidebar.append(self.section("Funcionarios", employee_scroll))

        self.editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.editor_box.add_css_class("editor-panel")
        
        right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        workspace.set_end_child(right_panel)

        carousel_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        carousel_container.add_css_class("month-carousel-container")
        
        carousel_title = Gtk.Label(label="Mês de Referência")
        carousel_title.add_css_class("section-title")
        carousel_container.append(carousel_title)
        
        self.month_carousel = Adw.Carousel()
        self.month_carousel.set_spacing(12)
        self.month_carousel.set_hexpand(True)
        self.month_carousel.set_allow_scroll_wheel(True)
        self.month_carousel.set_reveal_duration(250)
        self.month_carousel.connect("page-changed", self.on_month_carousel_page_changed)
        carousel_container.append(self.month_carousel)

        self.carousel_indicator = Adw.CarouselIndicatorDots()
        self.carousel_indicator.set_carousel(self.month_carousel)
        carousel_container.append(self.carousel_indicator)
        right_panel.append(carousel_container)

        editor_scroll = Gtk.ScrolledWindow()
        editor_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        editor_scroll.set_child(self.editor_box)
        editor_scroll.set_hexpand(True)
        editor_scroll.set_vexpand(True)
        right_panel.append(editor_scroll)

        self.add_drop_targets()
        self.refresh(force=True)
        threading.Thread(target=self.refresh_google_thread, daemon=True).start()
        GLib.timeout_add(500, self.refresh)

    def section(self, title: str, child: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("sidebar-section")
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("section-title")
        box.append(label)
        box.append(child)
        return box

    def add_drop_targets(self) -> None:
        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_drop_files)
        drop_target.connect("accept", self.on_drag_accept)
        drop_target.connect("leave", self.on_drag_leave)
        self.add_controller(drop_target)

        uri_target = Gtk.DropTarget.new(str, Gdk.DragAction.COPY)
        uri_target.connect("drop", self.on_drop_uri)
        uri_target.connect("accept", self.on_drag_accept)
        uri_target.connect("leave", self.on_drag_leave)
        self.add_controller(uri_target)

    def on_drag_accept(self, _target: Gtk.DropTarget, _drop: Gdk.Drop) -> Gdk.DragAction:
        self.overlay_box.set_visible(True)
        self.content_box.add_css_class("drop-active")
        return Gdk.DragAction.COPY

    def on_drag_leave(self, _target: Gtk.DropTarget) -> None:
        self.overlay_box.set_visible(False)
        self.content_box.remove_css_class("drop-active")

    def on_drop_files(self, target: Gtk.DropTarget, value: Gdk.FileList, _x: float, _y: float) -> bool:
        self.on_drag_leave(target)
        files = value.get_files()
        if not files:
            return False
        self.open_path_from_gfile(files[0])
        return True

    def on_drop_uri(self, target: Gtk.DropTarget, value: str, _x: float, _y: float) -> bool:
        self.on_drag_leave(target)
        for line in value.splitlines():
            line = line.strip()
            if line.startswith("file://"):
                self.open_path_from_gfile(Gio.File.new_for_uri(line))
                return True
            if os.path.exists(line):
                self.open_path(line)
                return True
        state.set_error("Nao consegui ler o arquivo arrastado.")
        self.refresh(force=True)
        return False

    def on_column_changed(self, spin_button: Gtk.SpinButton) -> None:
        state.set_name_column(spin_button.get_value_as_int())

    def on_load_clicked(self, _button: Gtk.Button) -> None:
        path = self.chooser.get_file_path()
        if not path:
            state.set_error("Selecione uma planilha Excel.")
            self.refresh(force=True)
            return
        self.open_path(path)

    def open_path_from_gfile(self, file: Gio.File) -> None:
        path = file.get_path()
        if not path:
            state.set_error("Nao consegui acessar esse arquivo pelo portal do Flatpak.")
            self.refresh(force=True)
            return
        self.chooser.set_file_path(path)
        self.open_path(path)

    def open_path(self, path: str) -> None:
        path = os.path.abspath(os.path.expanduser(path))
        if self._loading:
            return
        if not path.lower().endswith((".xlsx", ".xls")):
            state.set_error("Escolha uma planilha Excel (.xlsx ou .xls).")
            self.refresh(force=True)
            return

        self._loading = True
        state.set_status(f"Carregando {os.path.basename(path)}...")
        self.refresh(force=True)
        column = self.column_input.get_value_as_int()
        thread = threading.Thread(target=self.load_file_thread, args=(path, column), daemon=True)
        thread.start()

    def load_file_thread(self, path: str, column: int) -> None:
        try:
            result = state.load_file(path, col_nome=column)
            state.set_status(f"{len(result.get('months', []))} meses carregados de {os.path.basename(path)}.")
        except Exception as exc:
            traceback.print_exc()
            state.set_error(f"Erro ao processar o arquivo: {exc}")
        finally:
            self._loading = False
            GLib.idle_add(self.refresh, True)

    def refresh(self, force: bool = False) -> bool:
        snapshot = state.snapshot()
        if not force and snapshot["version"] == self._last_version:
            return True
        self._last_version = snapshot["version"]

        self.status_label.set_label(snapshot["status"])
        self.status_label.remove_css_class("error")
        if snapshot["error"]:
            self.status_label.add_css_class("error")

        has_escala = bool(snapshot["escala"])
        self.csv_button.set_sensitive(has_escala)
        self.ics_button.set_sensitive(has_escala)
        google_authenticated = bool(snapshot.get("google_status", {}).get("authenticated"))
        self.google_sync_button.set_sensitive(has_escala and google_authenticated and not self._google_busy)
        self.google_sync_sidebar_button.set_sensitive(has_escala and google_authenticated and not self._google_busy)
        self.calendar_combo.set_sensitive(google_authenticated and not self._google_busy)
        self.google_calendar_sidebar.set_sensitive(google_authenticated and not self._google_busy)
        self.settings_button.set_sensitive(not self._google_busy)
        self.settings_button_sidebar.set_sensitive(not self._google_busy)
        self.load_button.set_sensitive(not self._loading)
        if self._loading:
            self.spinner.start()
        else:
            self.spinner.stop()

        self.render_months(snapshot)
        self.render_employees(snapshot)
        self.render_google_calendars(snapshot)
        self.render_editor(snapshot)
        return True

    def render_google_calendars(self, snapshot: dict[str, Any]) -> None:
        calendars = snapshot.get("google_calendars") or []
        selected = snapshot.get("selected_google_calendar_id") or "primary"
        ids = [item["id"] for item in calendars] or ["primary"]
        if ids == self._calendar_ids:
            active_index = ids.index(selected) if selected in ids else 0
            if self.calendar_combo.get_active() != active_index:
                self.calendar_combo.set_active(active_index)
            if self.google_calendar_sidebar.get_active() != active_index:
                self.google_calendar_sidebar.set_active(active_index)
            return

        self._calendar_ids = ids
        self.calendar_combo.remove_all()
        self.google_calendar_sidebar.remove_all()
        if calendars:
            for item in calendars:
                label = item.get("summary", item["id"])
                if item.get("primary"):
                    label = f"{label} (principal)"
                self.calendar_combo.append_text(label)
                self.google_calendar_sidebar.append_text(label)
        else:
            self.calendar_combo.append_text("Principal")
            self.google_calendar_sidebar.append_text("Principal")
        self.calendar_combo.set_active(ids.index(selected) if selected in ids else 0)
        self.google_calendar_sidebar.set_active(ids.index(selected) if selected in ids else 0)
        status = snapshot.get("google_status") or {}
        if status.get("authenticated"):
            self.google_status_label.set_label(f'Conta conectada. {len(calendars)} agendas gravaveis.')
        elif status.get("configured"):
            self.google_status_label.set_label("Credenciais salvas, conta nao conectada.")
        else:
            self.google_status_label.set_label("Sem credenciais Google.")

    def on_month_carousel_page_changed(self, carousel: Adw.Carousel, index: int) -> None:
        if self._blocking_carousel_signal:
            return
        
        page = carousel.get_nth_page(index)
        for month_id, p in self._carousel_pages.items():
            if p == page:
                state.select_month(month_id)
                self.refresh(force=True)
                break

    def build_month_page(self, month: dict[str, Any]) -> Gtk.Widget:
        button = Gtk.Button()
        button.add_css_class("month-page")
        button.set_halign(Gtk.Align.CENTER)
        button.set_valign(Gtk.Align.CENTER)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("month-page-content")
        
        name = Gtk.Label(label=month["name"])
        name.add_css_class("section-title")
        
        month_number = month.get("month", "")
        month_label = f"{int(month_number):02d}" if str(month_number).isdigit() else str(month_number)
        meta = Gtk.Label(label=f'{month_label}/{month.get("year", "")}')
        meta.add_css_class("muted")
        
        box.append(name)
        box.append(meta)
        button.set_child(box)
        
        button.connect("clicked", lambda _btn, mid=month["id"]: self.on_month_clicked(mid))
        return button

    def on_month_clicked(self, month_id: str) -> None:
        if month_id in self._carousel_pages:
            state.select_month(month_id)
            self.refresh(force=True)

    def render_months(self, snapshot: dict[str, Any]) -> None:
        months = snapshot["months"]
        if not months:
            return

        month_ids = [m["id"] for m in months]
        if month_ids != self._last_month_ids:
            self._last_month_ids = month_ids
            # Limpa carrossel
            while True:
                child = self.month_carousel.get_nth_page(0)
                if child is None:
                    break
                self.month_carousel.remove(child)
            
            self._carousel_pages = {}
            for month in months:
                page = self.build_month_page(month)
                self.month_carousel.append(page)
                self._carousel_pages[month["id"]] = page
        
        # Sincroniza selecao
        selected_id = snapshot["selected_month_id"]
        for mid, page in self._carousel_pages.items():
            if mid == selected_id:
                page.add_css_class("selected")
            else:
                page.remove_css_class("selected")

        if selected_id in self._carousel_pages:
            target_page = self._carousel_pages[selected_id]
            current_pos = round(self.month_carousel.get_position())
            current_page = self.month_carousel.get_nth_page(current_pos)
            
            if target_page != current_page:
                self._blocking_carousel_signal = True
                # Usar False para evitar "fighting" com o timer de refresh
                self.month_carousel.scroll_to(target_page, False)
                self._blocking_carousel_signal = False

    def render_employees(self, snapshot: dict[str, Any]) -> None:
        clear_children(self.employee_list)
        employees = snapshot["employees"]
        if not employees:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="Selecione uma planilha e um mes.", xalign=0))
            self.employee_list.append(row)
            return

        for employee in employees:
            row = Gtk.ListBoxRow()
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            content.add_css_class("employee-row")
            if str(employee["id"]) == str(snapshot["selected_employee_id"]):
                content.add_css_class("selected")
            
            name = Gtk.Label(label=employee["name"], xalign=0, hexpand=True)
            name.add_css_class("employee-name")
            name.set_wrap(True)
            
            count = Gtk.Label(label=f'{employee.get("num_trabalho", 0)} dias')
            count.add_css_class("pill")
            
            content.append(name)
            content.append(count)
            row.set_child(content)
            
            # Usar GestureClick para garantir a captura do clique
            click = Gtk.GestureClick()
            click.connect("pressed", lambda _g, _n, _x, _y, eid=employee["id"]: self.select_employee(int(eid)))
            row.add_controller(click)
            
            self.employee_list.append(row)

    def render_editor(self, snapshot: dict[str, Any]) -> None:
        clear_children(self.editor_box)
        escala = snapshot["escala"]
        if not escala:
            self.editor_box.append(Gtk.Label(label="Carregue uma planilha e selecione um funcionario.", xalign=0))
            return

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_stack.set_hexpand(True)
        name = Gtk.Label(label=escala.get("name", "Funcionario"), xalign=0)
        name.set_markup(f"<big><b>{GLib.markup_escape_text(escala.get('name', 'Funcionario'))}</b></big>")
        name.set_wrap(True)
        month = Gtk.Label(label=escala.get("month_name", ""), xalign=0)
        month.add_css_class("muted")
        title_stack.append(name)
        title_stack.append(month)
        header.append(title_stack)

        header.append(Gtk.Label(label="Turno:"))
        turno_entry = Gtk.Entry()
        turno_entry.set_width_chars(10)
        turno_entry.set_text(escala.get("turno", "08x17"))
        turno_entry.connect("changed", lambda entry: state.set_turno(entry.get_text()))
        header.append(turno_entry)
        self.editor_box.append(header)

        turnos = snapshot.get("turnos") or {}
        if turnos:
            turno_box = Gtk.FlowBox()
            turno_box.set_selection_mode(Gtk.SelectionMode.NONE)
            turno_box.set_column_spacing(8)
            turno_box.set_row_spacing(8)
            for code, info in sorted(turnos.items()):
                label = f'{code}  {info.get("inicio", "")}-{info.get("fim", "")}'
                button = Gtk.Button(label=label)
                if code == escala.get("turno"):
                    button.add_css_class("suggested-action")
                button.connect("clicked", lambda _button, value=code: self.select_turno(value))
                turno_box.append(button)
            self.editor_box.append(self.section("Turnos", turno_box))

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_hexpand(True)
        self.editor_box.append(grid)

        for index, day in enumerate(escala.get("escala", [])):
            card = self.build_day_card(index, day)
            grid.attach(card, index % 4, index // 4, 1, 1)

    def build_day_card(self, index: int, day: dict[str, Any]) -> Gtk.Box:
        is_work = day.get("status") == "TRABALHO"
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("day-card")
        card.add_css_class("work" if is_work else "off")
        card.set_size_request(170, -1)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        number = Gtk.Label(label=str(day.get("day", "")), xalign=0, hexpand=True)
        number.add_css_class("day-number")
        weekday = Gtk.Label(label=WEEKDAYS.get(day.get("weekday"), day.get("weekday", "")))
        weekday.add_css_class("muted")
        top.append(number)
        top.append(weekday)
        card.append(top)

        toggle = Gtk.ToggleButton(label="Trabalho" if is_work else "Folga")
        toggle.set_active(is_work)
        toggle.connect("toggled", self.toggle_day_status, index)
        card.append(toggle)

        time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        start_entry = self.time_entry(day.get("start_time", "08:00"))
        end_entry = self.time_entry(day.get("end_time", "17:00"))
        start_entry.connect("changed", lambda entry, i=index: self.update_time(i, "start_time", entry.get_text()))
        end_entry.connect("changed", lambda entry, i=index: self.update_time(i, "end_time", entry.get_text()))
        time_row.append(start_entry)
        time_row.append(end_entry)
        card.append(time_row)

        colegas = day.get("colegas") or []
        if is_work:
            team_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            team_label = Gtk.Label(label="👥 Com o time:", xalign=0)
            team_label.add_css_class("muted")
            team_entry = Gtk.Entry()
            team_entry.set_placeholder_text("Ninguém no turno")
            team_entry.set_text(", ".join(colegas))
            team_entry.connect("activate", lambda entry, i=index: self.update_colegas(i, entry.get_text()))
            leave_ctrl = Gtk.EventControllerFocus.new()
            leave_ctrl.connect("leave", lambda _c, i=index, e=team_entry: self.update_colegas(i, e.get_text()))
            team_entry.add_controller(leave_ctrl)
            team_box.append(team_label)
            team_box.append(team_entry)
            card.append(team_box)

        return card

    def update_colegas(self, index: int, value: str) -> None:
        colegas = [n.strip().upper() for n in value.split(",") if n.strip()]
        state.update_day(index, colegas=colegas)

    def time_entry(self, value: str) -> Gtk.Entry:
        entry = Gtk.Entry()
        entry.set_text(value)
        entry.set_width_chars(5)
        entry.set_max_length(5)
        return entry

    def toggle_day_status(self, button: Gtk.ToggleButton, index: int) -> None:
        state.update_day(index, status="TRABALHO" if button.get_active() else "FOLGA")
        self.refresh(force=True)

    def update_time(self, index: int, key: str, value: str) -> None:
        if len(value) == 5 and value[2] == ":" and value[:2].isdigit() and value[3:].isdigit():
            state.update_day(index, **{key: value})

    def select_employee(self, employee_id: int) -> None:
        state.select_employee(employee_id)
        self.refresh(force=True)

    def select_turno(self, turno: str) -> None:
        state.set_turno(turno)
        self.refresh(force=True)

    def on_google_calendar_changed(self, combo: Gtk.ComboBoxText) -> None:
        active = combo.get_active()
        if active < 0 or active >= len(self._calendar_ids):
            return
        state.select_google_calendar(self._calendar_ids[active])

    def on_google_sync_clicked(self, _button: Gtk.Button) -> None:
        if self._google_busy:
            return
        self._google_busy = True
        state.set_status("Sincronizando com Google Calendar...")
        self.refresh(force=True)
        threading.Thread(target=self.google_sync_thread, daemon=True).start()

    def google_sync_thread(self) -> None:
        try:
            state.sync_google()
        except Exception as exc:
            traceback.print_exc()
            state.set_error(f"Erro no sync Google: {exc}")
        finally:
            self._google_busy = False
            GLib.idle_add(self.refresh, True)

    def refresh_google_thread(self) -> None:
        try:
            state.refresh_google()
        except Exception as exc:
            state.set_error(f"Erro ao carregar Google: {exc}")
        GLib.idle_add(self.refresh, True)

    def on_settings_clicked(self, _button: Gtk.Button) -> None:
        state.refresh_google()
        dialog = Adw.PreferencesDialog()
        dialog.set_title("Configuracoes")

        page = Adw.PreferencesPage()
        page.set_title("Google Agenda")
        dialog.add(page)

        group = Adw.PreferencesGroup()
        group.set_title("Conexao")
        page.add(group)

        snapshot = state.snapshot()
        google_status = snapshot.get("google_status") or {}
        status_text = "Conta conectada" if google_status.get("authenticated") else "Conta nao conectada"
        if not google_status.get("configured"):
            status_text = "Credenciais ausentes"

        status_row = Adw.ActionRow()
        status_row.set_title("Status")
        status_row.set_subtitle(status_text)
        group.add(status_row)

        path_row = Adw.ActionRow()
        path_row.set_title("Arquivo OAuth")
        path_row.set_subtitle(google_status.get("credentials_path", "backend/google_credential.json"))
        import_button = Gtk.Button(label="Importar JSON")
        import_button.connect("clicked", self.on_import_google_credentials_clicked, dialog)
        path_row.add_suffix(import_button)
        group.add(path_row)

        connect_row = Adw.ActionRow()
        connect_row.set_title("Conectar Google")
        connect_row.set_subtitle("Use OAuth Desktop ou autorize localhost no OAuth Web.")
        connect_button = Gtk.Button(label="Conectar")
        connect_button.connect("clicked", self.on_connect_google_clicked, dialog)
        connect_row.add_suffix(connect_button)
        group.add(connect_row)

        refresh_row = Adw.ActionRow()
        refresh_row.set_title("Agendas")
        refresh_row.set_subtitle(f'{len(snapshot.get("google_calendars") or [])} agendas gravaveis encontradas')
        refresh_button = Gtk.Button(label="Atualizar")
        refresh_button.connect("clicked", self.on_refresh_google_clicked, dialog)
        refresh_row.add_suffix(refresh_button)
        group.add(refresh_row)

        dialog.present(self.get_root())

    def on_import_google_credentials_clicked(self, _button: Gtk.Button, dialog: Adw.PreferencesDialog) -> None:
        file_dialog = Gtk.FileDialog.new()
        file_dialog.set_title("Selecione o OAuth Client JSON")
        file_filter = Gtk.FileFilter.new()
        file_filter.set_name("JSON")
        file_filter.add_pattern("*.json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        file_dialog.set_filters(filters)
        file_dialog.open(dialog, None, self.on_google_credentials_selected)

    def on_google_credentials_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        path = file.get_path() if file else None
        if not path:
            state.set_error("Nao consegui acessar o JSON escolhido.")
            self.refresh(force=True)
            return
        try:
            state.save_google_credentials(path)
            state.set_status("Credenciais Google salvas.")
        except Exception as exc:
            state.set_error(f"Erro ao salvar credenciais Google: {exc}")
        self.refresh(force=True)

    def on_connect_google_clicked(self, _button: Gtk.Button, _dialog: Adw.PreferencesDialog) -> None:
        if self._google_busy:
            return
        self._google_busy = True
        state.set_status("Abrindo autorizacao Google no navegador...")
        self.refresh(force=True)
        threading.Thread(target=self.connect_google_thread, daemon=True).start()

    def connect_google_thread(self) -> None:
        try:
            state.connect_google()
            state.set_status("Google Calendar conectado.")
        except Exception as exc:
            traceback.print_exc()
            state.set_error(f"Erro ao conectar Google: {exc}")
        finally:
            self._google_busy = False
            GLib.idle_add(self.refresh, True)

    def on_refresh_google_clicked(self, _button: Gtk.Button, _dialog: Adw.PreferencesDialog) -> None:
        try:
            state.refresh_google()
            state.set_status("Status Google atualizado.")
        except Exception as exc:
            state.set_error(f"Erro ao atualizar Google: {exc}")
        self.refresh(force=True)

    def save_export(self, kind: str) -> None:
        snapshot = state.snapshot()
        escala = snapshot.get("escala") or {}
        extension = "ics" if kind == "ics" else "csv"
        filename = f"{safe_filename(escala.get('name', ''), 'escala')}.{extension}"

        dialog = Gtk.FileDialog.new()
        dialog.set_title(f"Salvar {extension.upper()}")
        dialog.set_initial_name(filename)
        dialog.save(self.get_root(), None, lambda dlg, res, export_kind=kind: self.on_save_selected(dlg, res, export_kind))

    def on_save_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, kind: str) -> None:
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        path = file.get_path() if file else None
        if not path:
            state.set_error("Nao consegui acessar o destino escolhido.")
            self.refresh(force=True)
            return

        try:
            if kind == "ics":
                with open(path, "wb") as handle:
                    handle.write(state.export_ics())
            else:
                with open(path, "w", encoding="utf-8", newline="") as handle:
                    handle.write(state.export_csv())
            state.set_status(f"Arquivo salvo: {path}")
        except Exception as exc:
            state.set_error(f"Erro ao salvar arquivo: {exc}")
        self.refresh(force=True)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.set_default_size(1100, 760)
        self.set_title("Escala Local")

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        view = EscalaView()
        root.append(view)


class EscalaApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.ryse.EscalaWebEditor")
        self.connect("activate", self.on_activate)

    def on_activate(self, app: Adw.Application) -> None:
        install_css()
        self.window = MainWindow(application=app)
        self.window.present()


def main() -> int:
    app = EscalaApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
