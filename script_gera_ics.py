import os
import json
import pytz
import uuid
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event, vDatetime

# Configuração de caminhos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CALENDARS_DIR = os.path.join(BASE_DIR, "backend", "calendars")
DOCS_DIR = os.path.join(BASE_DIR, "docs")

# Fuso horário local
LOCAL_TZ = pytz.timezone('America/Sao_Paulo')

def generate_ics_content(data):
    """
    Gera o conteúdo de um arquivo .ics (iCalendar) ultra-compatível com Google Agenda
    """
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
                start_dt = LOCAL_TZ.localize(datetime.combine(data_obj, start_time_obj)).astimezone(timezone.utc)
                end_dt = LOCAL_TZ.localize(datetime.combine(data_obj, end_time_obj)).astimezone(timezone.utc)
                
                # Ajustar para virada de dia no turno 22x06
                if end_time_obj < start_time_obj:
                    end_dt += timedelta(days=1)
                    
                event = Event()
                event.add('summary', f'🏢 {name}')
                event.add('description', f'Escala de Trabalho\nTurno: {turno}\nGerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}')
                
                event.add('dtstart', start_dt)
                event.add('dtend', end_dt)
                event.add('dtstamp', now_utc)
                
                # UID fixo e único para evitar duplicação ou rejeição do Google
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

def main():
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
    
    if not os.path.exists(CALENDARS_DIR):
        print(f"Diretório {CALENDARS_DIR} não encontrado.")
        return

    # Processar cada JSON no diretório de calendários
    json_files = [f for f in os.listdir(CALENDARS_DIR) if f.endswith(".json")]
    
    if not json_files:
        print("Nenhum arquivo JSON encontrado para processar.")
        return

    for filename in json_files:
        json_path = os.path.join(CALENDARS_DIR, filename)
        ics_filename = filename.replace(".json", ".ics")
        ics_path = os.path.join(DOCS_DIR, ics_filename)
        
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            
            print(f"Gerando {ics_filename}...")
            ics_content = generate_ics_content(data)
            
            with open(ics_path, "wb") as f:
                f.write(ics_content)
            
            # Também criar um 'calendario.ics' genérico se for o único ou principal
            if len(json_files) == 1:
                generic_path = os.path.join(DOCS_DIR, "calendario.ics")
                with open(generic_path, "wb") as f:
                    f.write(ics_content)
                print(f"Copiado para calendario.ics")

        except Exception as e:
            print(f"Erro ao processar {filename}: {e}")

if __name__ == "__main__":
    main()
