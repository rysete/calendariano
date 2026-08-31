#!/usr/bin/env python3
"""
Script avançado para ler escala de funcionários do Excel e criar eventos no Google Calendar
Suporta múltiplos meses e funcionário favorito
"""

import pandas as pd
import sys
import os
import argparse
import json
import re
import calendar
from datetime import datetime, time
import pickle

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    Request = None
    Credentials = None
    InstalledAppFlow = None
    build = None
    HttpError = Exception

# Escopo necessário para o Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Arquivo para salvar funcionário favorito
FAVORITES_FILE = 'funcionario_favorito.json'

class EscalaProcessor:
    """Classe para processar dados de escala de funcionários"""
    
    def __init__(self, arquivo_excel, col_nome=0):
        self.arquivo_excel = arquivo_excel
        self.col_nome = col_nome
        self.turnos = {
            # Formatos completos
            'Operacional AWB - 06x14': {'inicio': '06:00', 'fim': '14:00'},
            'Operacional AWB - 14x22': {'inicio': '14:00', 'fim': '22:00'},
            'Operacional AWB - 22x06': {'inicio': '22:00', 'fim': '06:00'},
            'Operacional AWB- 06x14': {'inicio': '06:00', 'fim': '14:00'},
            'Operacional AWB-14x22': {'inicio': '14:00', 'fim': '22:00'},
            'Operacional AWB- 22x06': {'inicio': '22:00', 'fim': '06:00'},
            'Operacional HAWB': {'inicio': '08:00', 'fim': '17:00'},
            # Códigos de turno diretos
            '06x14': {'inicio': '06:00', 'fim': '14:00'},
            '14x22': {'inicio': '14:00', 'fim': '22:00'},
            '22x06': {'inicio': '22:00', 'fim': '06:00'},
            '08x16': {'inicio': '08:00', 'fim': '16:00'},
            '08x17': {'inicio': '08:00', 'fim': '17:00'},
            '07x15': {'inicio': '07:00', 'fim': '15:00'},
            '07X15': {'inicio': '07:00', 'fim': '15:00'},
        }
        
        # Mapeamento de nomes de abas para mês/ano
        self.meses_disponiveis = {}
        self._descobrir_meses()
    
    def _descobrir_meses(self):
        """
        Descobre automaticamente os meses válidos na planilha Excel,
        analisando cabeçalhos internos (A1:D4) e nomes de abas, ignorando abas vazias.
        """
        try:
            excel_file = pd.ExcelFile(self.arquivo_excel)
            meses_pt = {
                'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'MARCO': 3, 'MARZO': 3,
                'ABRIL': 4, 'MAIO': 5, 'MAYO': 5, 'JUNHO': 6, 'JULHO': 7,
                'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'OCTUBRO': 10,
                'NOVEMBRO': 11, 'DEZEMBRO': 12
            }
            meses_nomes = [
                '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
            ]
            
            ano_atual = datetime.now().year

            for sheet in excel_file.sheet_names:
                try:
                    df = pd.read_excel(self.arquivo_excel, sheet_name=sheet, header=None)
                except Exception:
                    continue

                if df.empty or df.shape[0] < 3 or df.shape[1] < 5:
                    continue

                mes_num = None
                ano_num = None

                # 1. Procurar mês e ano no topo da planilha (células A1..D4)
                candidates = []
                for r in range(min(4, len(df))):
                    for c in range(min(4, len(df.columns))):
                        val = df.iloc[r, c]
                        if pd.notna(val):
                            candidates.append(str(val).strip().upper())

                for cand in candidates:
                    for k, v in meses_pt.items():
                        if k in cand and not mes_num:
                            mes_num = v
                    ano_match = re.search(r'202[4-9]', cand)
                    if ano_match and not ano_num:
                        ano_num = int(ano_match.group())

                # 2. Se faltar mês ou ano, buscar no nome da aba
                sheet_upper = sheet.upper()
                if not mes_num:
                    for k, v in meses_pt.items():
                        if k in sheet_upper:
                            mes_num = v
                            break

                if not ano_num:
                    ano_match = re.search(r'202[4-9]', sheet_upper)
                    if ano_match:
                        ano_num = int(ano_match.group())
                    else:
                        ano_num = ano_atual

                if mes_num:
                    chave = f"{ano_num}-{mes_num:02d}"
                    nome_mes_formatado = f"{meses_nomes[mes_num]} {ano_num}"
                    
                    if chave not in self.meses_disponiveis:
                        self.meses_disponiveis[chave] = {
                            'nome': nome_mes_formatado,
                            'aba': sheet,
                            'mes': mes_num,
                            'ano': ano_num
                        }
                    else:
                        aba_existente = self.meses_disponiveis[chave]['aba']
                        if ('Sugest' in aba_existente or 'Atual' in aba_existente) and \
                           ('Sugest' not in sheet and 'Atual' not in sheet):
                            self.meses_disponiveis[chave] = {
                                'nome': nome_mes_formatado,
                                'aba': sheet,
                                'mes': mes_num,
                                'ano': ano_num
                            }
                        
        except Exception as e:
            print(f"⚠️  Aviso: Erro ao descobrir meses: {e}")
    
    def listar_meses(self):
        """
        Lista os meses disponíveis no arquivo
        """
        if not self.meses_disponiveis:
            print("❌ Nenhum mês encontrado no arquivo")
            return None
            
        print("\n=== MESES DISPONÍVEIS ===")
        meses_ordenados = sorted(self.meses_disponiveis.items())
        for i, (chave, info) in enumerate(meses_ordenados):
            print(f"{i+1}. {info['nome']} (aba: {info['aba']})")
        
        return meses_ordenados
    
    def ler_funcionarios_mes(self, mes_info):
        """
        Lê os funcionários e suas escalas de um mês específico
        com auto-detecção da linha de dias, coluna de nomes e horários.
        """
        print(f"\n📖 Lendo aba: {mes_info['aba']}")
        try:
            df = pd.read_excel(self.arquivo_excel, sheet_name=mes_info['aba'], header=None)
        except Exception as e:
            print(f"❌ Erro ao ler aba {mes_info['aba']}: {e}")
            return []
        
        ano = mes_info['ano']
        mes = mes_info['mes']
        from calendar import monthrange
        import re
        _, dias_no_mes = monthrange(ano, mes)
        
        # 1. Localizar dinamicamente a linha dos dias (1..31) e mapear coluna correspondente
        day_col_map = {}
        detected_name_col = None
        
        for r in range(min(15, len(df))):
            row = df.iloc[r]
            cols_found = {}
            for c in range(len(row)):
                val = row[c]
                if pd.isna(val):
                    continue
                
                day_num = None
                if isinstance(val, (int, float)) and 1 <= int(val) <= 31:
                    day_num = int(val)
                elif isinstance(val, (datetime, pd.Timestamp)):
                    day_num = val.day
                elif str(val).strip().isdigit() and 1 <= int(str(val).strip()) <= 31:
                    day_num = int(str(val).strip())
                
                if day_num and 1 <= day_num <= dias_no_mes:
                    cols_found[day_num] = c
                    
            if len(cols_found) >= 15:
                day_col_map = cols_found
                min_day_col = min(cols_found.values())
                detected_name_col = max(0, min_day_col - 1)
                break
                
        if not day_col_map:
            # Fallback seguro
            detected_name_col = 1 if len(df.columns) > 1 and df.iloc[:, 0].isna().mean() > 0.5 else 0
            for d in range(1, dias_no_mes + 1):
                day_col_map[d] = detected_name_col + d

        name_col_idx = self.col_nome if self.col_nome is not None and self.col_nome > 0 else detected_name_col
        if name_col_idx is None:
            name_col_idx = 0

        # 2. Extrair tabela de códigos de horário se presente no rodapé (ex: 1= 07:00 AS 15:00)
        codigo_horarios = {}
        for r in range(len(df)):
            for c in range(len(df.columns) - 1):
                v1 = str(df.iloc[r, c]).strip()
                m_code = re.match(r'^(\d{1,2})\s*=$', v1)
                if m_code:
                    code_num = m_code.group(1)
                    v2 = str(df.iloc[r, c+1]).strip()
                    m_time = re.search(r'(\d{1,2}:\d{2})\s*(?:AS|ÀS|-)\s*(\d{1,2}:\d{2})', v2, re.IGNORECASE)
                    if m_time:
                        codigo_horarios[code_num] = {
                            'inicio': m_time.group(1).zfill(5),
                            'fim': m_time.group(2).zfill(5)
                        }

        # 3. Ler funcionários e turnos
        funcionarios_data = []
        turno_atual = 'Operacional AWB - 08x17'
        
        palavras_excluir = {
            'JANEIRO', 'FEVEREIRO', 'MARÇO', 'MARCO', 'MARZO', 'ABRIL', 'MAIO', 'MAYO',
            'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'OCTUBRO', 
            'NOVEMBRO', 'DEZEMBRO', 'CCT', 'ESCALA', 'DOMINGOS', 'DOMINGO',
            'FERIADO', 'FERIADOS', 'TOTAL', 'IMPORTAÇÃO', 'IMPORTACAO', 'CAMPINAS',
            'NAN', 'HORÁRIOS', 'HORARIOS', 'FUNCIONÁRIOS', 'FUNCIONARIOS', 'DIAS',
            'SUPERVISOR', 'LIDER'
        }
        
        for r in range(len(df)):
            val_nome = df.iloc[r, name_col_idx] if name_col_idx < len(df.columns) else None
            # Fallback se a célula configurada for vazia
            if pd.isna(val_nome) and name_col_idx > 0:
                val_nome = df.iloc[r, 0]
            if pd.isna(val_nome) and name_col_idx == 0 and len(df.columns) > 1:
                val_nome = df.iloc[r, 1]
                
            if pd.isna(val_nome):
                continue
                
            texto_nome = str(val_nome).strip()
            if not texto_nome or texto_nome.lower() == 'nan':
                continue
                
            # Identificar cabeçalhos de turno em linha (ex: Operacional AWB- 06x14)
            if 'OPERACIONAL' in texto_nome.upper():
                turno_atual = texto_nome.strip()
                if '-' in turno_atual:
                    partes = turno_atual.split('-')
                    if len(partes) >= 2:
                        codigo_t = partes[-1].strip()
                        if codigo_t in self.turnos:
                            turno_atual = codigo_t
                continue
                
            # Filtrar totais, estatísticas e contadores
            if texto_nome.isdigit() or re.match(r'^\d+\s*DIAS', texto_nome, re.IGNORECASE) or re.match(r'^\d+\s*DOMINGOS', texto_nome, re.IGNORECASE):
                continue
                
            words = [w.strip() for w in re.split(r'[\s/]+', texto_nome.upper()) if w.strip()]
            if not words or all(w in palavras_excluir or w.isdigit() for w in words):
                continue
                
            if len(texto_nome) < 3 or not any(c.isalpha() for c in texto_nome):
                continue
                
            clean_name = re.sub(r'\s*/\s*\d+$', '', texto_nome).strip()
            
            # Identificar turno da linha
            turno_funcionario = turno_atual
            if len(df.columns) > 35 and pd.notna(df.iloc[r, 35]):
                t_val = str(df.iloc[r, 35]).strip()
                if t_val in self.turnos:
                    turno_funcionario = t_val
                    
            escala = {}
            dias_com_dados = 0
            
            for dia in range(1, dias_no_mes + 1):
                data_str = f"{ano}-{mes:02d}-{dia:02d}"
                col_idx = day_col_map.get(dia)
                cell_val = df.iloc[r, col_idx] if (col_idx is not None and col_idx < len(df.columns)) else None
                
                status = 'FOLGA'
                custom_time = None
                
                if pd.isna(cell_val):
                    status = 'FOLGA'
                else:
                    s_val = str(cell_val).strip().upper()
                    if s_val in ['F', 'FD', 'FF']:
                        status = 'FOLGA'
                    elif s_val == 'FE':
                        status = 'FERIADO'
                    elif s_val == 'FC':
                        status = 'FOLGA_COMPENSACAO'
                    elif s_val == 'FR':
                        status = 'FERIAS'
                    elif s_val in ['VA', 'CR']:
                        status = 'FOLGA'
                    elif s_val == 'DM':
                        status = 'DISPENSA_MEDICA'
                    elif s_val == 'X':
                        status = 'AUSENTE'
                    else:
                        num_match = re.match(r'^(\d+)(?:\.0)?$', s_val)
                        if num_match:
                            code_str = num_match.group(1)
                            status = 'TRABALHO'
                            if code_str in codigo_horarios:
                                custom_time = codigo_horarios[code_str]
                            elif code_str in self.turnos:
                                custom_time = self.turnos[code_str]
                        else:
                            status = 'TRABALHO'
                            
                if pd.notna(cell_val) and str(cell_val).strip():
                    dias_com_dados += 1
                    
                escala[data_str] = {
                    'status': status,
                    'start_time': custom_time['inicio'] if custom_time else None,
                    'end_time': custom_time['fim'] if custom_time else None,
                    'raw': str(cell_val) if pd.notna(cell_val) else ''
                }
                
            if dias_com_dados > 0:
                funcionarios_data.append({
                    'nome': clean_name,
                    'turno': turno_funcionario,
                    'escala': escala,
                    'mes_ano': mes_info['nome']
                })
        
        print(f"✅ {len(funcionarios_data)} funcionários encontrados")
        return funcionarios_data
    
    def mostrar_funcionarios(self, funcionarios):
        """
        Mostra lista de funcionários disponíveis
        """
        if not funcionarios:
            print("❌ Nenhum funcionário encontrado")
            return funcionarios
            
        print("\n=== FUNCIONÁRIOS DISPONÍVEIS ===")
        for i, func in enumerate(funcionarios):
            trabalho_dias = sum(
                1 for v in func['escala'].values() 
                if (isinstance(v, dict) and v.get('status') == 'TRABALHO') or v == 'TRABALHO'
            )
            print(f"{i+1}. {func['nome']} - {func['turno']} ({trabalho_dias} dias)")
        return funcionarios


class FuncionarioFavorito:
    """Classe para gerenciar funcionário favorito"""
    
    def __init__(self):
        self.arquivo_favoritos = FAVORITES_FILE
    
    def salvar_favorito(self, nome_funcionario):
        """Salva funcionário como favorito"""
        try:
            dados = {'funcionario_favorito': nome_funcionario}
            with open(self.arquivo_favoritos, 'w') as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            print(f"✅ {nome_funcionario} salvo como funcionário favorito")
        except Exception as e:
            print(f"⚠️  Não foi possível salvar favorito: {e}")
    
    def carregar_favorito(self):
        """Carrega funcionário favorito"""
        try:
            if os.path.exists(self.arquivo_favoritos):
                with open(self.arquivo_favoritos, 'r') as f:
                    dados = json.load(f)
                return dados.get('funcionario_favorito')
        except Exception as e:
            print(f"⚠️  Não foi possível carregar favorito: {e}")
        return None
    
    def tem_favorito(self):
        """Verifica se tem funcionário favorito"""
        return self.carregar_favorito() is not None


class GoogleCalendarManager:
    """Classe para gerenciar integração com Google Calendar"""
    
    def __init__(self):
        self.service = None
        self.credentials = None
    
    def authenticate(self):
        """Autentica com Google Calendar API"""
        if not all((Request, Credentials, InstalledAppFlow, build)):
            raise RuntimeError(
                "Dependencias do Google Calendar nao estao instaladas. "
                "A versao local GTK nao precisa delas; instale os pacotes google-* "
                "somente para usar a integracao direta com Google Calendar."
            )

        creds = None
        
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"\n⚠️  Erro ao usar o token salvo ({e}). Recriando autenticação...")
                    if os.path.exists('token.pickle'):
                        os.remove('token.pickle')
                    creds = None
                    
            if not creds:
                if not os.path.exists('credentials.json'):
                    raise Exception(
                        "Arquivo 'credentials.json' não encontrado!\n"
                        "Acesse o Google Cloud Console e baixe o JSON do tipo 'Aplicativo de desktop'."
                    )
                    
                # Verificar se o json está configurado como 'web' ao inves de 'installed'
                with open('credentials.json', 'r') as f:
                    content = f.read()
                    if '"web":' in content:
                        raise Exception(
                            "Erro: O seu 'credentials.json' é do tipo 'Aplicativo da Web'.\n"
                            "Por favor, volte no Google Cloud, exclua este e crie um novo ID de Cliente OAuth do tipo 'Aplicativo de desktop'."
                        )
                        
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=8080)
                
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        self.credentials = creds
        self.service = build('calendar', 'v3', credentials=creds)
        return True
    
    def listar_calendarios(self):
        """Lista os calendários disponíveis na conta Google autenticada"""
        if not self.service:
            print("❌ Erro: Não foi possível conectar ao Google Calendar")
            return []
            
        try:
            calendarios = []
            page_token = None
            while True:
                calendar_list = self.service.calendarList().list(pageToken=page_token).execute()
                for calendar_list_entry in calendar_list['items']:
                    calendarios.append({
                        'id': calendar_list_entry['id'],
                        'summary': calendar_list_entry['summary'],
                        'primary': calendar_list_entry.get('primary', False)
                    })
                page_token = calendar_list.get('nextPageToken')
                if not page_token:
                    break
            return calendarios
        except Exception as e:
            print(f"❌ Erro ao listar calendários: {e}")
            return []
            
    def criar_eventos_funcionario(self, funcionario_data, turno_info, horarios_customizados=None, calendar_id='primary'):
        """Cria eventos no calendário para um funcionário específico"""
        if not self.service:
            print("❌ Erro: Não foi possível conectar ao Google Calendar")
            return False
        
        nome = funcionario_data['nome']
        escala = funcionario_data['escala']
        turno = funcionario_data['turno']
        mes_ano = funcionario_data['mes_ano']
        
        print(f"\n📅 Criando eventos para {nome} - {mes_ano}...")
        eventos_criados = 0
        
        for data_str, status in escala.items():
            if status == 'TRABALHO':
                try:
                    data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
                    dia_do_mes = data_obj.day
                    
                    # Horários padrão do turno
                    hora_inicio_padrao = turno_info.get(turno, {}).get('inicio', '08:00')
                    hora_fim_padrao = turno_info.get(turno, {}).get('fim', '17:00')

                    hora_inicio = hora_inicio_padrao
                    hora_fim = hora_fim_padrao

                    # Verificar se há horário customizado para este dia
                    if horarios_customizados and dia_do_mes in horarios_customizados:
                        custom = horarios_customizados[dia_do_mes]
                        hora_inicio = custom['inicio']
                        # Usa o fim customizado se fornecido, senão mantém o padrão do turno
                        if custom['fim']:
                            hora_fim = custom['fim']
                    
                    start_datetime = datetime.combine(data_obj, datetime.strptime(hora_inicio, "%H:%M").time())
                    end_datetime = datetime.combine(data_obj, datetime.strptime(hora_fim, "%H:%M").time())
                    
                    # Se o turno vai até o próximo dia (22x06)
                    if hora_fim < hora_inicio:
                        from datetime import timedelta
                        end_datetime += timedelta(days=1)
                    
                    event = {
                        'summary': f'Trabalho - {nome}',
                        'description': f'Escala de trabalho - {turno}\nFuncionário: {nome}\nMês: {mes_ano}',
                        'start': {
                            'dateTime': start_datetime.isoformat(),
                            'timeZone': 'America/Sao_Paulo',
                        },
                        'end': {
                            'dateTime': end_datetime.isoformat(),
                            'timeZone': 'America/Sao_Paulo',
                        },
                        'colorId': '2',  # Verde para trabalho
                    }
                    
                    self.service.events().insert(calendarId=calendar_id, body=event).execute()
                    eventos_criados += 1
                    
                except Exception as e:
                    print(f"❌ Erro ao criar evento para {data_str}: {e}")
                    
        print(f"✅ {eventos_criados} eventos criados para {nome}")
        return True


def main():
    parser = argparse.ArgumentParser(description='Sincronizar escala de funcionários com Google Calendar')
    parser.add_argument('--funcionario', type=str, help='Nome do funcionário para sincronizar')
    parser.add_argument('--listar', action='store_true', help='Listar funcionários disponíveis')
    parser.add_argument('--mes', type=str, help='Mês para processar (ex: 2025-01)')
    parser.add_argument('--favorito', action='store_true', help='Usar funcionário favorito')
    parser.add_argument('--salvar-favorito', type=str, help='Salvar funcionário como favorito')
    parser.add_argument('--arquivo', type=str, 
                       default="excalibãããã.xlsx",
                       help='Caminho para o arquivo Excel da escala')
    parser.add_argument('--col-nome', type=int, default=0, help='Índice da coluna que contém os nomes dos funcionários (0=A, 1=B, etc)')
    parser.add_argument('-d', '--dias', type=str, help='Dias para aplicar horário customizado (separados por vírgula)')
    parser.add_argument('-H', '--horario', nargs='+', help='Horário customizado: 1 valor para entrada (HH:MM) ou 2 para entrada e saída (HH:MM HH:MM)')
    parser.add_argument('--confirmar', action='store_true', help='Confirmar automaticamente a sincronização com o Google Calendar')
    
    args = parser.parse_args()

    # Validar e processar horários customizados
    horarios_customizados = {}
    if args.dias and args.horario:
        if len(args.horario) > 2:
            print("❌ Erro: O argumento --horario aceita no máximo 2 valores (entrada e saída).")
            return 1
        
        try:
            dias = [int(d.strip()) for d in args.dias.split(',')]
            horario_inicio = datetime.strptime(args.horario[0], "%H:%M").time()
            horario_fim = datetime.strptime(args.horario[1], "%H:%M").time() if len(args.horario) == 2 else None
            
            for dia in dias:
                horarios_customizados[dia] = {
                    'inicio': horario_inicio.strftime("%H:%M"),
                    'fim': horario_fim.strftime("%H:%M") if horario_fim else None
                }
            print(f"✅ Horário customizado aplicado para os dias: {args.dias}")
        except ValueError:
            print("❌ Erro: Formato inválido para --dias ou --horario. Use dias como '15,20' e horário como 'HH:MM'.")
            return 1

    elif args.dias or args.horario:
        print("❌ Erro: Os argumentos --dias e --horario devem ser usados em conjunto.")
        return 1
    
    # Verificar se o arquivo existe
    if not os.path.exists(args.arquivo):
        print(f"❌ Erro: Arquivo não encontrado: {args.arquivo}")
        return 1
    
    # Criar processador de escala
    processor = EscalaProcessor(args.arquivo, col_nome=args.col_nome)
    favorito_manager = FuncionarioFavorito()
    
    # Escolher mês
    mes_selecionado = None
    if args.mes:
        if args.mes in processor.meses_disponiveis:
            mes_selecionado = processor.meses_disponiveis[args.mes]
        else:
            print(f"❌ Mês '{args.mes}' não encontrado")
            meses_lista = processor.listar_meses()
            return 1
    else:
        meses_lista = processor.listar_meses()
        if not meses_lista:
            return 1
        
        try:
            escolha_mes = int(input("\n🗓️  Digite o número do mês: ")) - 1
            if 0 <= escolha_mes < len(meses_lista):
                mes_selecionado = meses_lista[escolha_mes][1]
            else:
                print("❌ Número inválido")
                return 1
        except (ValueError, KeyboardInterrupt):
            print("\n❌ Operação cancelada")
            return 1
    
    print(f"\n📅 Mês selecionado: {mes_selecionado['nome']}")
    
    # Ler funcionários do mês selecionado
    funcionarios = processor.ler_funcionarios_mes(mes_selecionado)
    
    if not funcionarios:
        print("❌ Nenhum funcionário encontrado na escala")
        return 1
    
    # Listar funcionários se solicitado
    if args.listar:
        processor.mostrar_funcionarios(funcionarios)
        return 0
    
    # Escolher funcionário
    funcionario_selecionado = None
    
    # Se foi especificado para salvar favorito
    if args.salvar_favorito:
        for func in funcionarios:
            if args.salvar_favorito.upper() in func['nome'].upper():
                favorito_manager.salvar_favorito(func['nome'])
                return 0
        print(f"❌ Funcionário '{args.salvar_favorito}' não encontrado")
        return 1
    
    # Usar funcionário favorito se solicitado
    if args.favorito:
        nome_favorito = favorito_manager.carregar_favorito()
        if nome_favorito:
            for func in funcionarios:
                if nome_favorito.upper() in func['nome'].upper():
                    funcionario_selecionado = func
                    print(f"✅ Usando funcionário favorito: {nome_favorito}")
                    break
            
            if not funcionario_selecionado:
                print(f"❌ Funcionário favorito '{nome_favorito}' não encontrado neste mês")
        else:
            print("❌ Nenhum funcionário favorito salvo")
            return 1
    
    # Funcionário específico por argumento
    elif args.funcionario:
        for func in funcionarios:
            if args.funcionario.upper() in func['nome'].upper():
                funcionario_selecionado = func
                break
        
        if not funcionario_selecionado:
            print(f"❌ Funcionário '{args.funcionario}' não encontrado")
            processor.mostrar_funcionarios(funcionarios)
            return 1
    
    # Seleção interativa
    else:
        # Mostrar funcionário favorito se existir
        nome_favorito = favorito_manager.carregar_favorito()
        if nome_favorito:
            print(f"⭐ Funcionário favorito atual: {nome_favorito}")
        
        funcionarios_list = processor.mostrar_funcionarios(funcionarios)
        try:
            print("\n💡 Dica: Use --favorito para usar o funcionário favorito rapidamente")
            escolha = int(input("\n🔢 Digite o número do funcionário: ")) - 1
            if 0 <= escolha < len(funcionarios_list):
                funcionario_selecionado = funcionarios_list[escolha]
                
                # Perguntar se quer salvar como favorito
                if not nome_favorito or nome_favorito != funcionario_selecionado['nome']:
                    resposta = input(f"\n⭐ Salvar '{funcionario_selecionado['nome']}' como favorito? (s/N): ")
                    if resposta.lower() in ['s', 'sim', 'y', 'yes']:
                        favorito_manager.salvar_favorito(funcionario_selecionado['nome'])
            else:
                print("❌ Número inválido")
                return 1
        except (ValueError, KeyboardInterrupt):
            print("\n❌ Operação cancelada")
            return 1
    
    if not funcionario_selecionado:
        print("❌ Nenhum funcionário selecionado")
        return 1
    
    print(f"\n👤 Funcionário selecionado: {funcionario_selecionado['nome']}")
    print(f"🕐 Turno: {funcionario_selecionado['turno']}")
    print(f"📅 Mês: {funcionario_selecionado['mes_ano']}")
    
    # Mostrar resumo da escala
    trabalho_dias = sum(1 for status in funcionario_selecionado['escala'].values() if status == 'TRABALHO')
    folga_dias = sum(1 for status in funcionario_selecionado['escala'].values() 
                    if status in ['FOLGA', 'FOLGA_DESCANSO', 'FOLGA_COMPENSACAO'])
    ausente_dias = sum(1 for status in funcionario_selecionado['escala'].values() if status == 'AUSENTE')
    
    print(f"📊 Resumo: {trabalho_dias} dias de trabalho, {folga_dias} dias de folga, {ausente_dias} ausências")
    
    # Confirmar antes de sincronizar
    if not args.confirmar:
        resposta = input("\n❓ Confirma sincronização com Google Calendar? (s/N): ")
        if resposta.lower() not in ['s', 'sim', 'y', 'yes']:
            print("❌ Operação cancelada")
            return 0
    
    # Conectar com Google Calendar
    calendar_manager = GoogleCalendarManager()
    if not calendar_manager.authenticate():
        return 1
    
    print("✅ Conectado ao Google Calendar")
    
    # Criar eventos
    success = calendar_manager.criar_eventos_funcionario(funcionario_selecionado, processor.turnos, horarios_customizados)
    
    if success:
        print("\n🎉 Sincronização concluída com sucesso!")
        print("📱 Verifique seu Google Calendar para ver os eventos criados")
        
        # Dica para próxima vez
        if favorito_manager.tem_favorito():
            print(f"\n💡 Para próxima vez, use: python {os.path.basename(__file__)} --favorito --mes {mes_selecionado['ano']}-{mes_selecionado['mes']:02d}")
    else:
        print("\n❌ Erro durante a sincronização")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
