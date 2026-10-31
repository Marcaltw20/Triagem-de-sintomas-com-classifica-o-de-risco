"""
Configurações do backend (lidas do arquivo .env desta pasta).

Copie `.env.example` para `.env` e coloque o seu token da OpenAI em OPENAI_API_KEY.
"""
from __future__ import annotations

import os
import pathlib
import sys

from dotenv import load_dotenv

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent  # pasta "triagem_inteligente"

load_dotenv(AQUI / ".env")

# Pastas dos módulos que já existiam no projeto
PASTA_ARVORE = RAIZ / "arvore_decisao"
PASTA_PRESSAO = RAIZ / "pressao_arterial"
PASTA_REIDENTIFICACAO = RAIZ / "reidentificacao"
for p in (PASTA_ARVORE, PASTA_PRESSAO, PASTA_REIDENTIFICACAO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODELO_CHAT = os.getenv("MODELO_CHAT", "gpt-4o-mini")
MODELO_TRANSCRICAO = os.getenv("MODELO_TRANSCRICAO", "gpt-4o-mini-transcribe")
MODELO_VOZ = os.getenv("MODELO_VOZ", "gpt-4o-mini-tts")
VOZ = os.getenv("VOZ", "nova")
# Falas já geradas ficam guardadas aqui (frases fixas, como a saudação, só são pagas uma vez)
PASTA_CACHE_VOZ = AQUI / "cache_voz"
CACHE_VOZ_MAX = int(os.getenv("CACHE_VOZ_MAX", "200"))  # nº máximo de falas guardadas (0 = sem cache)

# Modo tempo real (voz -> voz, bem mais rápido)
MODO_PADRAO = os.getenv("MODO_PADRAO", "realtime")  # "realtime" ou "classico"
# gpt-realtime-mini custa ~1/3 do modelo grande (gpt-realtime-2.1); troque no .env se precisar de mais qualidade
MODELO_REALTIME = os.getenv("MODELO_REALTIME", "gpt-realtime-mini")
VOZ_REALTIME = os.getenv("VOZ_REALTIME", "marin")
SILENCIO_MS = int(os.getenv("SILENCIO_MS", "600"))  # silêncio para considerar que o usuário terminou de falar

# Pressão arterial
TEMPO_PRESSAO_S = int(os.getenv("TEMPO_PRESSAO_S", "120"))  # tempo para o usuário medir a pressão
OMRON_SIMULADO = os.getenv("OMRON_SIMULADO", "0") == "1"    # 1 = não usa o aparelho (valores fake)

# Saturação (SpO2) medida no Galaxy Watch (app em ../relogio_spo2), que envia POST /spo2 para este backend
TEMPO_SPO2_S = int(os.getenv("TEMPO_SPO2_S", "90"))      # tempo esperando a medição do relógio
SPO2_SIMULADO = os.getenv("SPO2_SIMULADO", "0") == "1"   # 1 = não usa o relógio (valores fake)
PASTA_DADOS = AQUI / "dados"                              # leituras do relógio (spo2_leituras.csv)

# Os valores acima são só os iniciais: depois a tela de configuração (/api/ajustes) grava
# backend/ajustes.json, que passa a valer no lugar deles.

# Valores padrão quando não há leitura do sensor (temperatura ainda não tem sensor)
SPO2_MANUAL = float(os.getenv("SPO2_MANUAL", "98"))
TEMP_MANUAL = float(os.getenv("TEMP_MANUAL", "36.5"))

# Câmera: confere se é a mesma pessoa do começo ao fim da triagem (backend/presenca.py)
USAR_CAMERA = os.getenv("USAR_CAMERA", "1") == "1"
CAMERA_SIMULADA = os.getenv("CAMERA_SIMULADA", "0") == "1"  # 1 = sem câmera (modo de teste)
CAMERA_INDICE = int(os.getenv("CAMERA_INDICE", "0"))         # 0 = primeira webcam
LIMIAR_CAMERA = float(os.getenv("LIMIAR_CAMERA", "0.40"))    # similaridade mínima para ser a mesma pessoa
TEMPO_TROCA_S = float(os.getenv("TEMPO_TROCA_S", "3"))       # outra pessoa por N s seguidos = cancela
TEMPO_ABANDONO_S = int(os.getenv("TEMPO_ABANDONO_S", "10"))  # titular fora por N s = cancela (0 = nunca)

# Banco de dados MySQL/MariaDB do XAMPP (backend/banco.py; esquema em ../banco/schema.sql)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")  # IP em vez de "localhost": no Windows falha mais rápido se o MySQL estiver desligado
DB_PORTA = int(os.getenv("DB_PORTA", "3306"))
DB_USUARIO = os.getenv("DB_USUARIO", "root")
DB_SENHA = os.getenv("DB_SENHA", "")  # o XAMPP vem com root sem senha
DB_NOME = os.getenv("DB_NOME", "triagem_inteligente")
SALVAR_NO_BANCO = os.getenv("SALVAR_NO_BANCO", "1") == "1"  # valor inicial; depois vale a tela de configuração
