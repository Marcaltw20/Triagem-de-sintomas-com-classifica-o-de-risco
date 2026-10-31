"""
Saturação de oxigênio (SpO2) vinda do Galaxy Watch (app em ../relogio_spo2).

O relógio mede e envia cada resultado para POST /spo2 deste backend (mesmo formato do antigo
server.py do projeto-spo2: {"spo2": 96, "timestamp": <ms>}). A leitura é guardada em memória
(a última) e no CSV backend/dados/spo2_leituras.csv.

Durante a triagem, o front-end chama `iniciar()` e fica consultando `ultima()` até chegar
uma leitura recebida depois do início. No modo de teste, `iniciar()` agenda uma leitura falsa.
"""
from __future__ import annotations

import asyncio
import csv
import datetime
import logging
import random
import socket
import time
from typing import Any

import config

log = logging.getLogger("spo2")

ARQUIVO_CSV = config.PASTA_DADOS / "spo2_leituras.csv"
ATRASO_SIMULADO_S = 6

_ultima: dict[str, Any] | None = None
_simulacao: asyncio.Task | None = None


def agora_ms() -> int:
    return int(time.time() * 1000)


def _salvar_csv(leitura: dict[str, Any]) -> None:
    ARQUIVO_CSV.parent.mkdir(parents=True, exist_ok=True)
    novo = not ARQUIVO_CSV.exists()
    with ARQUIVO_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["relogio_timestamp_ms", "relogio_horario_utc", "spo2", "recebido_em_utc", "simulado"])
        utc = datetime.timezone.utc
        w.writerow([leitura["timestamp"],
                    datetime.datetime.fromtimestamp(leitura["timestamp"] / 1000, tz=utc).isoformat(),
                    leitura["spo2"],
                    datetime.datetime.fromtimestamp(leitura["recebido_em_ms"] / 1000, tz=utc).isoformat(),
                    leitura["simulado"]])


def registrar(spo2: int, timestamp: int, simulado: bool = False) -> dict[str, Any]:
    """Guarda uma leitura recebida do relógio (ou simulada)."""
    global _ultima
    if not 0 <= spo2 <= 100:
        raise ValueError("spo2 precisa estar entre 0 e 100")
    if timestamp <= 0:
        raise ValueError("timestamp precisa ser positivo")
    _ultima = {"spo2": spo2, "timestamp": timestamp, "recebido_em_ms": agora_ms(), "simulado": simulado}
    _salvar_csv(_ultima)
    log.info("SpO2 recebido%s: %s%%", " (simulado)" if simulado else "", spo2)
    return _ultima


def ultima() -> dict[str, Any] | None:
    return _ultima


async def _simular() -> None:
    await asyncio.sleep(ATRASO_SIMULADO_S)
    registrar(random.randint(94, 99), agora_ms(), simulado=True)


def iniciar(simulado: bool) -> int:
    """Marca o início de uma medição; devolve o horário (ms) a partir do qual a leitura vale."""
    global _simulacao
    inicio = agora_ms()
    if simulado:
        if _simulacao and not _simulacao.done():
            _simulacao.cancel()
        _simulacao = asyncio.get_running_loop().create_task(_simular())
    return inicio


def ip_local() -> str:
    """IP deste computador na rede local (o relógio precisa dele no SERVER_URL)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # não envia nada; só escolhe a interface da rede local
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
