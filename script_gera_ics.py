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

    # Monta os eventos primeiro para poder derivar timestamps deterministicos.
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

            start_dt = LOCAL_TZ.localize(datetime.combine(data_obj, start_time_obj)).astimezone(timezone.utc)
            end_dt = LOCAL_TZ.localize(datetime.combine(data_obj, end_time_obj)).astimezone(timezone.utc)

            # Ajustar para virada de dia no turno 22x06
            if end_time_obj < start_time_obj:
                end_dt += timedelta(days=1)

            eventos.append((data_str, start_dt, end_dt))
        except Exception as e:
            print(f"Erro ao processar dia {data_str}: {e}")

    if not eventos:
        return cal.to_ical()

    # Timestamps derivados dos dados (nao de "agora"), para que o mesmo JSON
    # sempre gere exatamente o mesmo .ics. Sem isso, todo push gera um commit
    # novo so por causa do DTSTAMP.
    inicio = min(e[1] for e in eventos)
    fim = max(e[1] for e in eventos)
    stamp = fim
    periodo = (
        inicio.astimezone(LOCAL_TZ).strftime("%d/%m/%Y")
        + " - "
        + fim.astimezone(LOCAL_TZ).strftime("%d/%m/%Y")
    )
    descricao = f"Escala de Trabalho\nTurno: {turno}\nPeriodo: {periodo}"

    safe_name = "".join(c for c in name if c.isalnum())

    for data_str, start_dt, end_dt in eventos:
        event = Event()
        event.add('summary', f'🏢 {name}')
        event.add('description', descricao)

        event.add('dtstart', start_dt)
        event.add('dtend', end_dt)
        event.add('dtstamp', stamp)

        # UID fixo e único para evitar duplicação ou rejeição do Google
        event.add('uid', f"{data_str}-{safe_name}@escala.web.ryse.io")

        event.add('status', 'CONFIRMED')
        event.add('transp', 'OPAQUE')
        event.add('sequence', 0)

        cal.add_component(event)

    return cal.to_ical()

def pick_principal(json_files):
    """
    Escolhe qual JSON gera o 'calendario.ics' principal.

    Prioridade:
      1. arquivo chamado 'calendario.json'
      2. o JSON modificado mais recentemente (o ultimo publicado)
    """
    principal_name = "calendario.json"
    if principal_name in json_files:
        return principal_name
    newest = max(json_files, key=lambda f: os.path.getmtime(os.path.join(CALENDARS_DIR, f)))
    return newest


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

    principal = pick_principal(json_files)

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
            
            # O calendario.ics principal é sempre gerado (a partir do JSON principal)
            if filename == principal:
                generic_path = os.path.join(DOCS_DIR, "calendario.ics")
                with open(generic_path, "wb") as f:
                    f.write(ics_content)
                print(f"Copiado para calendario.ics (principal: {filename})")

        except Exception as e:
            print(f"Erro ao processar {filename}: {e}")

if __name__ == "__main__":
    main()
