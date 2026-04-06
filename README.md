# Escala Web Editor 📅

Uma solução web completa e interativa para gerenciar, editar e sincronizar escalas de trabalho a partir de planilhas Excel para o Google Agenda.

## 🚀 Funcionalidades

- **Upload Dinâmico:** Arraste e solte planilhas `.xlsx` diretamente no navegador.
- **Editor Interativo:** Clique nos dias para alternar entre TRABALHO e FOLGA.
- **Edição de Turno Textual:** Digite o turno (ex: `14x22`) e o sistema auto-preenche os horários de todos os dias.
- **Exportação Flexível:**
  - Baixe o arquivo **CSV** para importação manual.
  - Baixe o arquivo **ICS (iCalendar)** para testes locais.
  - **Link de Agenda (WebCal):** Gere uma URL permanente para assinar no Google Agenda com atualização automática.
- **Túnel Integrado:** Suporte a Cloudflare Tunnel embutido para permitir que o Google Agenda acesse seu servidor local com segurança.

## 🛠️ Stack Tecnológica

- **Backend:** Python (FastAPI) + logic de processamento `openpyxl`.
- **Frontend:** React + TypeScript + Vite + Lucide Icons.
- **Infra:** Docker & Docker Compose.
- **Sincronização:** iCalendar (ICS) com suporte a ETag e Cache-Control.

## 📦 Como Rodar (via Docker)

A forma recomendada de rodar é usando Docker, pois ele já configura o banco de dados temporário e o túnel de internet.

1. **Subir a Stack:**
   ```bash
   cd escala-web-editor
   docker-compose up -d --build
   ```

2. **Acessar Localmente:**
   Abra [http://localhost:8001](http://localhost:8001) no seu navegador.

3. **Obter Link Público (para Google Agenda):**
   Para que o Google consiga ler sua agenda, você precisa usar a URL do túnel:
   ```bash
   docker logs escala-web-tunnel
   ```
   Copie a URL que termina em `.trycloudflare.com`. Acesse o sistema por essa URL para gerar links compatíveis com o Google.

## 🔄 Comandos Úteis

- **Ligar/Desligar o Túnel:**
  ```bash
  docker stop escala-web-tunnel  # Desliga
  docker start escala-web-tunnel # Liga
  ```
- **Ver Logs do App:**
  ```bash
  docker logs -f escala-web-app
  ```
- **Desenvolvimento (Live Reload):**
  A pasta `backend` está mapeada no container. Qualquer alteração no código Python é aplicada instantaneamente sem reiniciar o Docker.

## 📂 Estrutura de Pastas

- `backend/`: API FastAPI e lógica de ponte com o processador de escala.
- `backend/calendars/`: (Persistente) Onde ficam salvas as escalas editadas.
- `backend/uploads/`: (Persistente) Cache das planilhas enviadas.
- `frontend/`: Código fonte do React (Vite).
- `frontend-dist/`: Pasta onde o build final do React é servido pelo FastAPI.

---
Desenvolvido para simplificar a gestão de horários e integração com o ecossistema Google.
