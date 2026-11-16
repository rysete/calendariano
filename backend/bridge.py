import os
import pandas as pd
from datetime import datetime, date, timedelta
import json
import csv
import zlib
from io import StringIO

try:
    from .vendor.escala_calendar_v2 import EscalaProcessor
except ImportError:
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../escala-google-calendar")))
    from escala_calendar_v2 import EscalaProcessor

EXCEL_FILE = os.getenv(
    "ESCALA_DEFAULT_EXCEL",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../escala-google-calendar/excalibãããã.xlsx")),
)

class EscalaBridge:
    def __init__(self, excel_path=EXCEL_FILE, col_nome=0):
        self.excel_path = excel_path
        self.col_nome = col_nome
        self.processor = EscalaProcessor(self.excel_path, col_nome=self.col_nome)
        self._funcionarios_cache = {}
        self._schedule_blocks_cache = {}

    def _get_funcionarios_mes(self, month_id):
        if month_id not in self.processor.meses_disponiveis:
            return []
        if month_id not in self._funcionarios_cache:
            mes_info = self.processor.meses_disponiveis[month_id]
            self._funcionarios_cache[month_id] = self.processor.ler_funcionarios_mes(mes_info)
        return self._funcionarios_cache[month_id]

    def get_months(self):
        months = []
        for key, info in sorted(self.processor.meses_disponiveis.items()):
            months.append({
                "id": key,
                "name": info["nome"],
                "aba": info["aba"],
                "year": info["ano"],
                "month": info["mes"]
            })
        return months

    def get_employees(self, month_id):
        funcionarios = self._get_funcionarios_mes(month_id)
        if not funcionarios:
            return []
        
        result = []
        for i, func in enumerate(funcionarios):
            num_trabalho = sum(
                1 for v in func["escala"].values()
                if (isinstance(v, dict) and v.get("status") == "TRABALHO") or v == "TRABALHO"
            )
            result.append({
                "id": i,
                "name": func.get("nome", "Funcionário"),
                "turno": func.get("turno", "08x17"),
                "num_trabalho": num_trabalho
            })
        return result

    @staticmethod
    def is_pseudo_employee(nome):
        if not nome:
            return True
        clean = str(nome).strip().lower()
        return clean.startswith("total") or clean.startswith("resumo") or clean == ""

    def get_month_schedule_blocks(self, month_id):
        if not hasattr(self, "_schedule_blocks_cache"):
            self._schedule_blocks_cache = {}
        if month_id in self._schedule_blocks_cache:
            return self._schedule_blocks_cache[month_id]

        funcionarios = self._get_funcionarios_mes(month_id)
        if not funcionarios:
            return {}

        por_data = {}
        for other_func in funcionarios:
            other_name = other_func.get("nome", other_func.get("name", "")).strip()
            if self.is_pseudo_employee(other_name):
                continue
            other_turno = other_func.get("turno", "08x17")
            other_turno_info = self.processor.turnos.get(other_turno, {"inicio": "08:00", "fim": "17:00"})
            for d_str, d_val in other_func.get("escala", {}).items():
                if isinstance(d_val, dict):
                    d_status = d_val.get("status", "FOLGA")
                    d_st = d_val.get("start_time") or other_turno_info.get("inicio", "08:00")
                    d_et = d_val.get("end_time") or other_turno_info.get("fim", "17:00")
                else:
                    d_status = str(d_val)
                    d_st = other_turno_info.get("inicio", "08:00")
                    d_et = other_turno_info.get("fim", "17:00")

                if d_status == "TRABALHO":
                    bloco = (d_st, d_et)
                    por_data.setdefault(d_str, {}).setdefault(bloco, set()).add(other_name)

        self._schedule_blocks_cache[month_id] = por_data
        return por_data

    def get_colegas(self, month_id, date_str, start_time, end_time, exclude_name=""):
        por_data = self.get_month_schedule_blocks(month_id)
        bloco = (start_time, end_time)
        colegas_set = por_data.get(date_str, {}).get(bloco, set())
        exclude_clean = exclude_name.strip().lower()
        return sorted([n for n in colegas_set if n.strip().lower() != exclude_clean])

    def get_turnos(self):
        return self.processor.turnos

    def get_escala(self, month_id, employee_id):
        funcionarios = self._get_funcionarios_mes(month_id)
        if not funcionarios:
            return None
        
        if employee_id < 0 or employee_id >= len(funcionarios):
            return None
        
        func = funcionarios[employee_id]
        escala_list = []
        
        # Obter o nome com segurança
        nome_func = func.get("nome", func.get("name", "Funcionário"))
        
        # Ordenar os dias
        for date_str, item in sorted(func["escala"].items()):
            data_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Obter horários padrão do turno
            turno_info = self.processor.turnos.get(func["turno"], {"inicio": "08:00", "fim": "17:00"})
            
            if isinstance(item, dict):
                status = item.get("status", "FOLGA")
                start_time = item.get("start_time") or turno_info.get("inicio", "08:00")
                end_time = item.get("end_time") or turno_info.get("fim", "17:00")
            else:
                status = str(item)
                start_time = turno_info.get("inicio", "08:00")
                end_time = turno_info.get("fim", "17:00")
            
            colegas = self.get_colegas(month_id, date_str, start_time, end_time, nome_func)

            escala_list.append({
                "date": date_str,
                "day": data_obj.day,
                "weekday": data_obj.strftime("%A"),
                "status": status,
                "start_time": start_time,
                "end_time": end_time,
                "colegas": colegas
            })
            
        return {
            "name": nome_func,
            "turno": func.get("turno", "08x17"),
            "month_name": func.get("mes_ano", ""),
            "escala": escala_list
        }

    def generate_csv_content(self, data):
        """
        Gera o conteúdo do CSV a partir do JSON recebido do frontend
        """
        output = StringIO()
        fieldnames = ['Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 
                     'All Day Event', 'Description', 'Location', 'Private']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        name = data.get("name", "Funcionario")
        turno = data.get("turno", "N/A")
        mes_ano = data.get("month_name", "")
        
        for item in data.get("escala", []):
            if item.get("status") == "TRABALHO":
                data_str = item.get("date")
                hora_inicio = item.get("start_time", "08:00")
                hora_fim = item.get("end_time", "17:00")
                
                data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
                start_datetime = datetime.combine(data_obj, datetime.strptime(hora_inicio, "%H:%M").time())
                end_datetime = datetime.combine(data_obj, datetime.strptime(hora_fim, "%H:%M").time())
                
                if hora_fim < hora_inicio:
                    end_datetime += timedelta(days=1)
                
                writer.writerow({
                    'Subject': f'Trabalho - {name}',
                    'Start Date': start_datetime.strftime('%m/%d/%Y'),
                    'Start Time': start_datetime.strftime('%I:%M %p'),
                    'End Date': end_datetime.strftime('%m/%d/%Y'),
                    'End Time': end_datetime.strftime('%I:%M %p'),
                    'All Day Event': 'False',
                    'Description': (
                        f'Escala de trabalho - Turno: {turno} - Funcionário: {name} - Mês: {mes_ano}'
                        + (f' - Com o time: {", ".join(item.get("colegas") or [])}'
                           if item.get("colegas") else '')
                    ),
                    'Location': '',
                    'Private': 'False'
                })
        
        return output.getvalue()

    def generate_ics_content(self, data):
        """
        Gera o conteúdo de um arquivo .ics (iCalendar) ultra-compatível com Google Agenda,
        com timestamps e sequence determinísticos.
        """
        from icalendar import Calendar, Event
        from datetime import datetime, timezone, timedelta
        import pytz

        local_tz = pytz.timezone('America/Sao_Paulo')

        cal = Calendar()
        cal.add('prodid', '-//Escala Web Editor//ryse.io//PT')
        cal.add('version', '2.0')
        cal.add('method', 'PUBLISH')
        cal.add('x-wr-calname', f"Escala {data.get('name', 'Trabalho')}")
        cal.add('x-wr-timezone', 'America/Sao_Paulo')
        cal.add('calscale', 'GREGORIAN')

        name = data.get("name", "Funcionario")
        turno = data.get("turno", "N/A")

        eventos = []
        for item in data.get("escala", []):
            if item.get("status") != "TRABALHO":
                continue
            data_str = item.get("date")
            hora_inicio = item.get("start_time", "08:00")
            hora_fim = item.get("end_time", "17:00")

            try:
                data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
                start_time_obj = datetime.strptime(hora_inicio, "%H:%M").time()
                end_time_obj = datetime.strptime(hora_fim, "%H:%M").time()

                start_dt = local_tz.localize(datetime.combine(data_obj, start_time_obj)).astimezone(timezone.utc)
                end_dt = local_tz.localize(datetime.combine(data_obj, end_time_obj)).astimezone(timezone.utc)

                if end_time_obj < start_time_obj:
                    end_dt += timedelta(days=1)

                eventos.append((data_str, start_dt, end_dt, item.get("colegas") or []))
            except Exception as e:
                print(f"Erro ao processar dia {data_str}: {e}")

        if not eventos:
            return cal.to_ical()

        inicio = min(e[1] for e in eventos)
        fim = max(e[1] for e in eventos)
        stamp = fim
        periodo = (
            inicio.astimezone(local_tz).strftime("%d/%m/%Y")
            + " - "
            + fim.astimezone(local_tz).strftime("%d/%m/%Y")
        )
        safe_name = "".join(c for c in name if c.isalnum())

        for data_str, start_dt, end_dt, colegas in eventos:
            if colegas:
                linhas = [
                    "Escala de Trabalho",
                    f"Turno: {turno}",
                    "Com o time: " + ", ".join(colegas),
                    f"Periodo: {periodo}",
                ]
            else:
                linhas = ["Escala de Trabalho", f"Turno: {turno}", f"Periodo: {periodo}"]
            descricao = "\n".join(linhas)

            event = Event()
            event.add('summary', f'🏢 {name}')
            event.add('description', descricao)

            event.add('dtstart', start_dt)
            event.add('dtend', end_dt)
            event.add('dtstamp', stamp)

            uid = f"{data_str}-{safe_name}@escala.web.ryse.io"
            event.add('uid', uid)

            content_hash = zlib.crc32(f"{start_dt.isoformat()}{end_dt.isoformat()}{descricao}".encode("utf-8"))
            sequence_num = content_hash % 100000

            event.add('status', 'CONFIRMED')
            event.add('transp', 'OPAQUE')
            event.add('sequence', sequence_num)
            event.add('last-modified', stamp)

            cal.add_component(event)

        return cal.to_ical()
