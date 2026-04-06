#!/bin/bash

# Cores para o output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

ROOT_DIR=$(pwd)

echo -e "${BLUE}🚀 Iniciando Escala Web Editor...${NC}"

# Função para encerrar todos os processos ao sair
cleanup() {
    echo -e "\n${BLUE}🛑 Encerrando processos...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}

trap cleanup SIGINT

# 1. Preparar Backend
echo -e "${BLUE}📦 Preparando ambiente do Backend...${NC}"
cd "$ROOT_DIR/backend"
if [ ! -d "venv" ]; then
    echo -e "${BLUE}⚙️ Criando virtualenv...${NC}"
    python3 -m venv venv
fi

echo -e "${BLUE}📥 Instalando dependências (isso pode levar um momento)...${NC}"
./venv/bin/pip install -r requirements.txt -q

echo -e "${GREEN}📡 Iniciando Backend (FastAPI) na porta 8001...${NC}"
./venv/bin/python3 main.py &
BACKEND_PID=$!

# 2. Preparar Frontend
echo -e "${BLUE}💻 Preparando Frontend...${NC}"
cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}📥 Instalando node_modules...${NC}"
    npm install --silent
fi

echo -e "${GREEN}✨ Iniciando Frontend (Vite) na porta 5173...${NC}"
npm run dev &
FRONTEND_PID=$!

echo -e "${GREEN}✅ Tudo pronto! Acesse: http://localhost:5173${NC}"
echo -e "${BLUE}Pressione Ctrl+C para encerrar.${NC}"

wait
