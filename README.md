# Escala Web Editor 📅

Uma solução web completa e interativa para gerenciar, editar e sincronizar escalas de trabalho a partir de planilhas Excel para o Google Agenda.

## 🚀 Funcionalidades

- **Upload Dinâmico:** Arraste e solte planilhas `.xlsx` diretamente no navegador.
- **Editor Interativo:** Clique nos dias para alternar entre TRABALHO e FOLGA.
- **Edição de Turno Textual:** Digite o turno (ex: `14x22`) e o sistema auto-preenche os horários de todos os dias.
- **Exportação Flexível:**
  - Baixe o arquivo **CSV** para importação manual.
  - Baixe o arquivo **ICS (iCalendar)** para testes locais.
  - **Automação via GitHub Pages:** Publique sua escala e deixe o Google Agenda atualizar sozinho sem servidor ligado 24h.

## 🛠️ Stack Tecnológica

- **Backend:** Python (FastAPI) + logic de processamento `openpyxl`.
- **Frontend:** React + TypeScript + Vite + Lucide Icons.
- **Infra:** Docker & Docker Compose.
- **Automação:** GitHub Actions + GitHub Pages para hospedagem estática de arquivos `.ics`.

## 📦 Como Rodar (via Docker)

1. **Subir a Stack:**
   ```bash
   cd escala-web-editor
   docker-compose up -d --build
   ```

2. **Acessar Localmente:**
   Abra [http://localhost:8001](http://localhost:8001) no seu navegador.

## 🤖 Automação de Calendário (GitHub Pages)

Para que o Google Agenda atualize sua escala sem você precisar de um servidor ligado, usamos o GitHub Actions.

### Como funciona:
1. Você gera a escala no Web Editor (salva como JSON em `backend/calendars/`).
2. Você faz o `git push` desse arquivo JSON para o seu repositório no GitHub.
3. O GitHub Actions detecta a mudança, gera o arquivo `.ics` e o publica no GitHub Pages.
4. O Google Agenda lê o arquivo `.ics` diretamente do seu GitHub Pages.

### Fluxo de Trabalho (Workflow):
Sempre que salvar uma escala nova:
```bash
git add 'backend/calendars/*.json'
git commit -m "update: nova escala de trabalho"
git push
```

### URLs da sua Agenda:
- **Principal:** `https://rysete.github.io/calendariano/calendario.ics`
- **Por Usuário:** `https://rysete.github.io/calendariano/NOME_DO_ARQUIVO.ics`

*Nota: O Google Agenda pode levar de 8h a 24h para atualizar automaticamente. Para forçar a atualização imediata ao adicionar, use `.../calendario.ics?v=1`.*

## 📂 Estrutura de Pastas

- `backend/calendars/`: Onde ficam salvos os arquivos JSON das escalas (rastreados pelo Git).
- `docs/`: Pasta servida pelo GitHub Pages contendo os arquivos `.ics` gerados.
- `.github/workflows/`: Automação que transforma JSON em ICS.
- `script_gera_ics.py`: O "motor" de conversão que roda no GitHub Actions.

---
Desenvolvido para simplificar a gestão de horários e integração com o ecossistema Google via infraestrutura serverless do GitHub.
