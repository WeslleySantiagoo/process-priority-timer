#!/usr/bin/env bash
set -euo pipefail

if [[ -t 1 ]]; then
	COLOR_RESET='\033[0m'
	COLOR_INFO='\033[36m'
	COLOR_SUCCESS='\033[32m'
	COLOR_WARN='\033[33m'
	COLOR_ERROR='\033[31m'
	COLOR_TITLE='\033[1;34m'
else
	COLOR_RESET=''
	COLOR_INFO=''
	COLOR_SUCCESS=''
	COLOR_WARN=''
	COLOR_ERROR=''
	COLOR_TITLE=''
fi

info() {
	echo -e "${COLOR_INFO}[INFO] $*${COLOR_RESET}"
}

success() {
	echo -e "${COLOR_SUCCESS}[OK] $*${COLOR_RESET}"
}

warn() {
	echo -e "${COLOR_WARN}[AVISO] $*${COLOR_RESET}"
}

error() {
	echo -e "${COLOR_ERROR}[ERRO] $*${COLOR_RESET}"
}

title() {
	echo -e "${COLOR_TITLE}$*${COLOR_RESET}"
}

if [[ "${EUID}" -ne 0 ]]; then
	error "Este script só pode ser executado com sudo para fazer operações no nice dos processos."
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
title "Process Priority Timer"
info "Verificando configuração dos processos..."

ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
	set -a
	# shellcheck disable=SC1090
	source "${ENV_FILE}"
	set +a
	success "Arquivo .env carregado com sucesso."
else
	warn "Arquivo .env não encontrado. Usando valores padrão."
fi

: "${VALOR_TARGET:=990000000}"
: "${TIME_TARGET:=60}"
: "${BASE_SCRIPT:=base-lidiano.py}"
: "${MEU_SCRIPT:=main.py}"
: "${CPU_BASE:=0}"
: "${CPU_MEU:=0}"
: "${CPU_MONITOR:=1}"
: "${MONITOR_INTERVAL:=0.1}"
: "${MONITOR_THRESHOLD:=0.1}"

# Chamada dos scripts com sudo explícito para garantir permissões de renice
sudo env VALOR_TARGET="${VALOR_TARGET}" taskset -c "${CPU_BASE}" \
	python3 "${SCRIPT_DIR}/${BASE_SCRIPT}" &
PID_BASE=$!

success "Processo base iniciado: ${BASE_SCRIPT} (PID ${PID_BASE}) na CPU ${CPU_BASE}."

# O main.py agora roda o monitor no seu próprio processo pai
sudo nice -n -19 env VALOR_TARGET="${VALOR_TARGET}" TIME_TARGET="${TIME_TARGET:-60}" \
    CPU_MONITOR="${CPU_MONITOR}" MONITOR_INTERVAL="${MONITOR_INTERVAL:-1.0}" \
    MONITOR_THRESHOLD="${MONITOR_THRESHOLD:-1.0}" \
    taskset -c "${CPU_MEU}" python3 "${SCRIPT_DIR}/${MEU_SCRIPT}" &
PID_YOURS=$!

success "Seu script iniciado: ${MEU_SCRIPT} (PID ${PID_YOURS}) na CPU ${CPU_MEU}."

warn "Os dois processos estão rodando em paralelo; acompanhe a saída para comparar o comportamento."

info "Aguardando término dos processos..."
wait "$PID_BASE"
wait "$PID_YOURS"

success "Execução concluída."
