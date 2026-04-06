# --- Stage 1: Build Frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Ajustar API_BASE para apontar para o host interno ou variável de ambiente se necessário
RUN npm run build

# --- Stage 2: Final Image ---
FROM python:3.11-slim
WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt-cache/*

# Copiar Backend
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
# Criar pasta de uploads
RUN mkdir -p /app/backend/uploads

# Copiar Frontend Build para ser servido pelo FastAPI (opcional) ou manter separado
# Aqui vamos manter a estrutura para rodar os dois
COPY --from=frontend-build /app/frontend/dist ./frontend-dist

# Script de inicialização
COPY run_web_editor.sh ./
RUN chmod +x run_web_editor.sh

# Expor portas
EXPOSE 8001 5173

# Variável para o link da agenda (pode ser seu IP ou domínio)
ENV EXTERNAL_URL="http://localhost:8001"

CMD ["python", "backend/main.py"]
