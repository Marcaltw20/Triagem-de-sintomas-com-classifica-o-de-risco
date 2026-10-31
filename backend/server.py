"""
Servidor da triagem por voz (FastAPI).

Este arquivo só monta o servidor. A API usada pelo front-end está em api.py
(rotas) e schemas.py (formatos de entrada e saída); a documentação está em ../API.md.

Como rodar (dentro da pasta backend):
  uvicorn server:app --host 0.0.0.0 --port 8000
(--host 0.0.0.0 deixa o Galaxy Watch, na mesma rede Wi-Fi, enviar o SpO2 para POST /spo2)
Com o servidor rodando, http://localhost:8000/docs mostra e testa todas as rotas.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

import config  # noqa: F401  (carrega o .env e as pastas da árvore e do Omron antes de importar a API)
import banco
import presenca
from api import relogio, router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")



@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    # cria o banco e as tabelas no MySQL do XAMPP, se ele estiver ligado (senão só avisa no log)
    await run_in_threadpool(banco.inicializar)
    yield
    presenca.encerrar()  # libera a câmera ao desligar o backend


app = FastAPI(title="Triagem por voz - TCC 2026", lifespan=ciclo_de_vida)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(relogio)
