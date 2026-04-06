import sys
import os
import pandas as pd
from datetime import datetime, date, timedelta
import json
import csv
from io import StringIO

# Adicionar o diretório pai ao sys.path para importar a lógica existente
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../escala-google-calendar")))

try:
    from escala_calendar_v2 import EscalaProcessor
except ImportError:
    # Se falhar, tenta o caminho absoluto se soubermos onde estamos
    sys.path.append("/home/ryse/gemini/escala-google-calendar")
    from escala_calendar_v2 import EscalaProcessor

EXCEL_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../escala-google-calendar/excalibãããã.xlsx"))

class EscalaBridge:
    def __init__(self, excel_path=EXCEL_FILE):
        self.excel_path = excel_path
        self.processor = EscalaProcessor(self.excel_path)

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
        if month_id not in self.processor.meses_disponiveis:
            return []
        
        mes_info = self.processor.meses_disponiveis[month_id]
        funcionarios = self.processor.ler_funcionarios_mes(mes_info)
        
        result = []
        for i, func in enumerate(funcionarios):
            result.append({
                "id": i,
                "name": func.get("nome", "Funcionário"),
                "turno": func.get("turno", "08x17"),
                "num_trabalho": sum(1 for status in func["escala"].values() if status == "TRABALHO")
            })
        return result

    def get_turnos(self):
        return self.processor.turnos

    def get_escala(self, month_id, employee_id):
        if month_id not in self.processor.meses_disponiveis:
            return None
        
        mes_info = self.processor.meses_disponiveis[month_id]
        funcionarios = self.processor.ler_funcionarios_mes(mes_info)
        
        if employee_id < 0 or employee_id >= len(funcionarios):
            return None
        
        func = funcionarios[employee_id]
        escala_list = []
        
        # Obter o nome com segurança
        nome_func = func.get("nome", func.get("name", "Funcionário"))
        
        # Ordenar os dias
        for date_str, status in sorted(func["escala"].items()):
            data_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Obter horários padrão do turno
            turno_info = self.processor.turnos.get(func["turno"], {"inicio": "08:00", "fim": "17:00"})
            
            escala_list.append({
                "date": date_str,
                "day": data_obj.day,
                "weekday": data_obj.strftime("%A"),
                "status": status,
                "start_time": turno_info.get("inicio", "08:00"),
                "end_time": turno_info.get("fim", "17:00")
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
                    'Subject': f'🏢 Trabalho - {name}',
                    'Start Date': start_datetime.strftime('%m/%d/%Y'),
                    'Start Time': start_datetime.strftime('%I:%M %p'),
                    'End Date': end_datetime.strftime('%m/%d/%Y'),
                    'End Time': end_datetime.strftime('%I:%M %p'),
                    'All Day Event': 'False',
                    'Description': f'Escala de trabalho - Turno: {turno} - Funcionário: {name} - Mês: {mes_ano}',
                    'Location': '',
                    'Private': 'False'
                })
        
        return output.getvalue()

    def generate_ics_content(self, data):
        """
        Gera o conteúdo de um arquivo .ics (iCalendar) ultra-compatível com Google Agenda
        """
        from icalendar import Calendar, Event, vDatetime
        import uuid
        from datetime import datetime, timezone, timedelta
        import pytz
        
        # Fuso horário local
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
        
        now_utc = datetime.now(timezone.utc)
        
        for item in data.get("escala", []):
            if item.get("status") == "TRABALHO":
                data_str = item.get("date")
                hora_inicio = item.get("start_time", "08:00")
                hora_fim = item.get("end_time", "17:00")
                
                try:
                    # Parsear data e horas
                    data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
                    start_time_obj = datetime.strptime(hora_inicio, "%H:%M").time()
                    end_time_obj = datetime.strptime(hora_fim, "%H:%M").time()
                    
                    # Criar datetimes localizados e converter para UTC
                    # Google prefere datas em UTC com o sufixo 'Z'
                    start_dt = local_tz.localize(datetime.combine(data_obj, start_time_obj)).astimezone(timezone.utc)
                    end_dt = local_tz.localize(datetime.combine(data_obj, end_time_obj)).astimezone(timezone.utc)
                    
                    # Ajustar para virada de dia no turno 22x06
                    if end_time_obj < start_time_obj:
                        end_dt += timedelta(days=1)
                        
                    event = Event()
                    event.add('summary', f'🏢 {name}')
                    event.add('description', f'Escala de Trabalho\nTurno: {turno}\nGerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}')
                    
                    # Usar vDatetime para garantir o formato ISO em UTC (Z)
                    event.add('dtstart', start_dt)
                    event.add('dtend', end_dt)
                    event.add('dtstamp', now_utc)
                    
                    # UID fixo e único para evitar duplicação ou rejeição do Google
                    # O domínio @escala.web ajuda na validação
                    safe_name = "".join(c for c in name if c.isalnum())
                    uid = f"{data_str}-{safe_name}@escala.web.ryse.io"
                    event.add('uid', uid)
                    
                    event.add('status', 'CONFIRMED')
                    event.add('transp', 'OPAQUE')
                    event.add('sequence', 0)
                    
                    cal.add_component(event)
                except Exception as e:
                    print(f"Erro ao processar dia {data_str}: {e}")
        
        return cal.to_ical()
