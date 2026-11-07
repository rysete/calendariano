# Escala Local

Editor local single-user para carregar planilhas Excel de escala, ajustar dias/horarios e exportar CSV ou ICS para agenda.

## Funcionalidades

- App local em GTK 4/Libadwaita, sem servidor web embutido.
- Carregamento por botao nativo e drag-and-drop da janela GTK.
- Editor de dias para alternar Trabalho/Folga e ajustar horarios.
- Exportacao CSV e ICS.

## Stack

- Python + PyGObject/GTK 4 + Libadwaita para a janela nativa, seguindo a base do FFMBEATER GTK.
- `pandas`, `openpyxl` e o processador vendorizado em `backend/vendor/`.
- Flatpak para instalacao local.

## Como Rodar

### App GTK local

Use o venv do backend e abra a janela GTK/libadwaita:

```bash
backend/venv/bin/python -m pip install -r requirements.txt
./run_native.sh
```

No host local, o GTK/PyGObject vem do sistema. Em Arch, por exemplo, instale `gtk4` e `python-gobject` se `./run_native.sh` nao abrir a janela.

### App web local auxiliar

Use este modo para rodar a versao web sem container. Ele compila o frontend, sobe o FastAPI servindo o bundle final e abre `http://127.0.0.1:8765` no navegador:

```bash
./run_local_web.sh
```

Para Google Agenda neste modo, cadastre no Google Cloud exatamente:

```text
http://127.0.0.1:8765/api/google/callback
```

Se mudar a porta com `ESCALA_WEB_EDITOR_PORT`, cadastre a URI com a mesma porta.

### Flatpak local

Cria e instala o app no usuario:

```bash
./build-flatpak.sh
```

Depois rode pelo menu do sistema ou pelo terminal:

```bash
flatpak run org.ryse.EscalaWebEditor
```

O app abre a interface GTK/libadwaita nativa e grava logs em `~/escala-local.log`.

### Smoke test

```bash
bash scripts/native-smoke.sh
```

O teste importa a camada nativa, carrega uma planilha, seleciona a primeira escala e valida exportacao CSV/ICS.

## Google Agenda direto

A versao web e o app GTK nativo tem sync direto com Google Calendar, alem do link ICS/webcal.

No app GTK:

1. Abra `Configuracoes`.
2. Importe o OAuth Client JSON.
3. Clique em `Conectar`.
4. Depois de autorizado, clique em `Atualizar`.
5. Escolha a agenda no seletor do topo e use `Sync Google`.

Para o GTK, prefira um OAuth Client do tipo `Desktop app`. Se usar `Web application`, cadastre tambem o redirect local `http://127.0.0.1:8766/` ou use o fluxo web auxiliar.

Fluxo:

1. No Google Cloud Console, crie um OAuth Client do tipo `Web application`.
2. Em `Authorized redirect URIs`, cadastre exatamente a URL mostrada em `Configuracoes > Google Redirect URI`.
   - App web local: `http://127.0.0.1:8765/api/google/callback`
   - Container local: `http://127.0.0.1:8001/api/google/callback`
   - Tunnel: use a URL `https://...trycloudflare.com/api/google/callback` mostrada pelo app.
3. Baixe o JSON do OAuth Client.
4. No app web, abra `Configuracoes`, envie o `Google OAuth Client JSON` e clique em `Conectar Google`.
5. Depois de autorizar, clique em `Atualizar status`, escolha o calendario e use `Sync Google`.

O sync usa IDs determinísticos por funcionario/data, entao sincronizar de novo atualiza eventos existentes em vez de duplicar. Dias alterados para folga removem o evento correspondente.

## 🤖 Automação de Calendário (GitHub Pages)

Para que o Google Agenda atualize sua escala sem você precisar de um servidor ligado, usamos o GitHub Actions.

### Como funciona:
1. Você gera a escala no Web Editor (salva como JSON em `backend/calendars/`).
2. Você faz o `git push` desse arquivo JSON para o seu repositório no GitHub.
3. O GitHub Actions detecta a mudança, gera o arquivo `.ics` e o publica no GitHub Pages.
4. O Google Agenda lê o arquivo `.ics` diretamente do seu GitHub Pages.

### Fluxo de Trabalho (Workflow):

**Jeito rápido (comando `escala-publicar`)** — faz tudo em uma tacada:
```bash
escala-publicar "~/Downloads/ESCALA CCT CAMPINAS IMPORTAÇÃO - OUTUBRO 2026 (2).xlsx" --funcionario RYAN
```
Esse comando lê a planilha, gera `backend/calendars/<nome>.json`, gera o `.ics`, faz
commit/push e espera o GitHub Pages publicar. Opções úteis:
- `--desde YYYY-MM` / `--ate YYYY-MM` publicam uma faixa de meses
- `--todos` publica todos os meses da planilha
- `--sem-push` só gera os arquivos locais
- `--dry-run` mostra o que seria publicado sem gravar nada

**Por padrão só o mês corrente é publicado** — a escala dos meses seguintes fica de
fora até a vez, para não publicar turno provisório no Agenda. Quando chegar a
planilha do mês novo, é só rodar o comando de novo.

**Jeito manual:**
```bash
git add 'backend/calendars/*.json'
git commit -m "update: nova escala de trabalho"
git push
```

### URLs da sua Agenda:
- **Principal:** `https://rysete.github.io/calendariano/calendario.ics`
- **Por Usuário:** `https://rysete.github.io/calendariano/NOME_DO_ARQUIVO.ics`

O `calendario.ics` é sempre gerado a partir do JSON mais recente em
`backend/calendars/` (ou de um arquivo chamado `calendario.json`, se existir).

*Nota: O Google Agenda pode levar de 8h a 24h para atualizar automaticamente. Para forçar a atualização imediata ao adicionar, use `.../calendario.ics?v=1`.*

## 📂 Estrutura de Pastas

- `backend/calendars/`: Onde ficam salvos os arquivos JSON das escalas (rastreados pelo Git).
- `docs/`: Pasta servida pelo GitHub Pages contendo os arquivos `.ics` gerados.
- `.github/workflows/`: Automação que transforma JSON em ICS.
- `script_gera_ics.py`: O "motor" de conversão que roda no GitHub Actions.

---
Desenvolvido para simplificar a gestão de horários e integração com o ecossistema Google via infraestrutura serverless do GitHub.
