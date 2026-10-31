"""
Banco de dados MySQL/MariaDB (XAMPP) da triagem.

O esquema está em ../banco/schema.sql (feito a partir do diagrama de classes). Ao iniciar, o
backend chama `inicializar()`, que cria o banco e as tabelas se ainda não existirem e preenche os
catálogos a partir da árvore de decisão (sintomas, fatores de risco e as 27 regras de combinação)
e os dispositivos a partir da tela de configuração.

Se o MySQL estiver desligado, a triagem continua funcionando normalmente, só não grava nada; a
próxima gravação tenta conectar de novo. Conexão configurada no .env (DB_HOST, DB_PORTA, DB_USUARIO,
DB_SENHA, DB_NOME). Gravar ou não fica na tela de configuração ("Salvar as triagens no banco").

  inicializar()              cria banco/tabelas e sincroniza catálogos e dispositivos
  estado()                   conectado? quantas triagens? último erro
  salvar_triagem(...)        grava paciente, triagem, sintomas, fatores, leituras e classificação
  salvar_encaminhamento(...) grava a triagem encerrada na identificação (encaminhada à enfermagem)
  salvar_cancelamento(...)   grava a triagem cancelada pela câmera (outra pessoa assumiu o totem)
  ultimas_triagens(n)        as n triagens mais recentes (tela de configuração)
  buscar_usuario(email) ...  login da tela de configuração (autenticacao.py)
"""
from __future__ import annotations

import ast
import datetime
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

import ajustes
import config

log = logging.getLogger("banco")

ARQUIVO_SCHEMA = config.RAIZ / "banco" / "schema.sql"
ARQUIVO_ARVORE = config.PASTA_ARVORE / "arvore_decisao.py"
ID_RELOGIO = "relogio"
ESPERA_APOS_FALHA_S = 30  # com o MySQL desligado, não tenta conectar em toda triagem (cada tentativa demora)

_trava = threading.Lock()
_pronto = False
_ultimo_erro: str | None = None
_falhou_em = 0.0


class BancoIndisponivel(RuntimeError):
    pass


def _conectar(com_banco: bool = True) -> pymysql.connections.Connection:
    return pymysql.connect(host=config.DB_HOST, port=config.DB_PORTA, user=config.DB_USUARIO,
                           password=config.DB_SENHA, database=config.DB_NOME if com_banco else None,
                           charset="utf8mb4", cursorclass=DictCursor, connect_timeout=3, autocommit=False)


@contextmanager
def _transacao() -> Iterator[pymysql.cursors.Cursor]:
    """Abre conexão e cursor; confirma no fim ou desfaz tudo se der erro."""
    if not _pronto and not inicializar():
        raise BancoIndisponivel(_ultimo_erro)
    con = _conectar()
    try:
        with con.cursor() as cur:
            yield cur
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Criação do banco e dos catálogos
# --------------------------------------------------------------------------- #

def _comandos_schema() -> list[str]:
    sql = ARQUIVO_SCHEMA.read_text(encoding="utf-8")
    sql = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    sql = sql.replace("triagem_inteligente", config.DB_NOME)  # caso o nome do banco mude no .env
    return [c.strip() for c in sql.split(";") if c.strip()]


def _regras_combinacao() -> list[dict[str, str]]:
    """As 27 regras da árvore, com a condição copiada do próprio código (arvore_decisao.py)."""
    fonte = ARQUIVO_ARVORE.read_text(encoding="utf-8")
    listas = {"COMBINACOES_ALARME": "VERMELHO", "COMBINACOES_MUITO_URGENTES": "LARANJA",
              "COMBINACOES_MODERADAS": "AMARELO"}
    regras = []
    for no in ast.parse(fonte).body:
        alvo = getattr(no, "target", None) or (no.targets[0] if isinstance(no, ast.Assign) else None)
        nome = getattr(alvo, "id", None)
        if nome not in listas or not isinstance(no.value, ast.List):
            continue
        for i, item in enumerate(no.value.elts, start=1):
            motivo = ast.literal_eval(item.elts[0])
            condicao = ast.get_source_segment(fonte, item.elts[1].body)
            regras.append({"id": f"{listas[nome]}_{i:02d}", "cor": listas[nome], "motivo": motivo[:255],
                           "condicao": re.sub(r"\s+", " ", condicao)})
    return regras


def _sincronizar_catalogos(cur) -> None:
    from arvore_decisao import CATALOGO

    for grupo, itens in CATALOGO.items():
        for chave, rotulo, descricao, cor in itens:
            if cor is None:
                cur.execute("INSERT INTO fator_risco (chave, descricao) VALUES (%s, %s) "
                            "ON DUPLICATE KEY UPDATE descricao = VALUES(descricao)", (chave, descricao))
            else:
                cur.execute("INSERT INTO sintoma (chave, rotulo, descricao, grupo, cor_base) VALUES (%s, %s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE rotulo = VALUES(rotulo), descricao = VALUES(descricao), "
                            "grupo = VALUES(grupo), cor_base = VALUES(cor_base)",
                            (chave, rotulo, descricao, grupo, cor))
    for r in _regras_combinacao():
        cur.execute("INSERT INTO regra_combinacao (id, condicao, cor, motivo) VALUES (%s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE condicao = VALUES(condicao), cor = VALUES(cor), motivo = VALUES(motivo)",
                    (r["id"], r["condicao"], r["cor"], r["motivo"]))


def _sincronizar_dispositivos(cur) -> None:
    """Medidores cadastrados na tela de configuração + o relógio viram linhas de `dispositivo`."""
    a = ajustes.ler()
    linhas = [(m["id"], m["nome"], "MONITOR_PA", ajustes.MODELOS.get(m["modelo"], m["modelo"]), "BLE", m["endereco"])
              for m in a["medidores"]]
    linhas.append((ID_RELOGIO, "Relógio do totem", "RELOGIO", "Samsung Galaxy Watch 6", "WIFI_HTTP", None))
    for linha in linhas:
        cur.execute("INSERT INTO dispositivo (identificador, nome, tipo, modelo, protocolo, endereco) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE nome = VALUES(nome), "
                    "modelo = VALUES(modelo), endereco = VALUES(endereco)", linha)


def inicializar(forcar: bool = False) -> bool:
    """Cria banco, tabelas e catálogos. Devolve False (sem levantar erro) se o MySQL não responder."""
    global _pronto, _ultimo_erro, _falhou_em
    with _trava:
        if not forcar and time.monotonic() - _falhou_em < ESPERA_APOS_FALHA_S:
            return False
        try:
            con = _conectar(com_banco=False)
            try:
                with con.cursor() as cur:
                    for comando in _comandos_schema():
                        cur.execute(comando)
                    _sincronizar_catalogos(cur)
                    _sincronizar_dispositivos(cur)
                con.commit()
            finally:
                con.close()
        except Exception as exc:  # noqa: BLE001
            _pronto, _ultimo_erro, _falhou_em = False, str(exc), time.monotonic()
            log.warning("Banco de dados indisponível (%s). A triagem segue sem gravar.", exc)
            return False
        _pronto, _ultimo_erro = True, None
        log.info("Banco '%s' pronto em %s:%s", config.DB_NOME, config.DB_HOST, config.DB_PORTA)
        return True


def sincronizar_dispositivos() -> None:
    """Chamado quando a tela de configuração cadastra/remove medidores."""
    if not _pronto:
        return
    try:
        with _transacao() as cur:
            _sincronizar_dispositivos(cur)
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui atualizar os dispositivos no banco: %s", exc)


# --------------------------------------------------------------------------- #
# Gravação
# --------------------------------------------------------------------------- #

def _data_nascimento(texto: str | None) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(texto or "", "%d/%m/%Y").date()
    except ValueError:
        return None


def _salvar_paciente(cur, paciente: dict[str, Any], perfil: dict[str, Any]) -> int:
    cpf = re.sub(r"\D", "", paciente.get("cpf") or "")
    if len(cpf) != 11 or not (paciente.get("nome") or "").strip():
        raise ValueError("nome ou CPF do paciente ausente/inválido; triagem não gravada")
    cur.execute(
        "INSERT INTO paciente (nome, cpf, data_nascimento, idade, sexo) VALUES (%s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id), nome = VALUES(nome), "
        "data_nascimento = VALUES(data_nascimento), idade = VALUES(idade), sexo = VALUES(sexo)",
        (paciente["nome"].strip().upper(), cpf,
         _data_nascimento(paciente.get("data_nascimento")), perfil.get("idade"), perfil.get("sexo")))
    return cur.lastrowid


def _id_dispositivo(cur, identificador: str | None) -> int | None:
    if not identificador:
        return None
    cur.execute("SELECT id FROM dispositivo WHERE identificador = %s", (identificador,))
    linha = cur.fetchone()
    return linha["id"] if linha else None


def salvar_triagem(registro: dict[str, Any], perfil: dict[str, Any], resultado: dict[str, Any]) -> int:
    """Grava uma triagem concluída. `resultado` é a saída de arvore_decisao.classificar_risco."""
    from arvore_decisao import COR_BASE

    vitais = resultado["dados"]["vitais"]
    chaves = resultado["dados"]["sintomas"]  # já inclui fatores do perfil (ex.: idoso)
    medidor = ajustes.medidor_ativo()
    modo = registro.get("modo_questionario")

    with _transacao() as cur:
        _sincronizar_dispositivos(cur)
        paciente_id = _salvar_paciente(cur, registro["paciente"], perfil)
        cur.execute(
            "INSERT INTO triagem (paciente_id, modo_questionario, resumo_relato, status, deficiencias, conversa) "
            "VALUES (%s, %s, %s, 'CONCLUIDA', %s, %s)",
            (paciente_id, modo, registro.get("resumo"), ",".join(perfil.get("deficiencias") or []) or None,
             json.dumps(registro.get("conversa") or [], ensure_ascii=False)))
        triagem_id = cur.lastrowid

        for chave in chaves:
            if COR_BASE.get(chave) is None:
                cur.execute("INSERT IGNORE INTO triagem_fator_risco (triagem_id, fator_risco_chave) VALUES (%s, %s)",
                            (triagem_id, chave))
            else:
                cur.execute("INSERT IGNORE INTO sintoma_relatado (triagem_id, sintoma_chave, origem) VALUES (%s, %s, %s)",
                            (triagem_id, chave, modo))

        # leitura 1: medidor de pressão; leitura 2: saturação (relógio) e temperatura
        pressao_sensor = registro.get("pressao_origem") == "SENSOR"
        spo2_sensor = registro.get("spo2_origem") == "SENSOR"
        cur.execute(
            "INSERT INTO leitura_sinais_vitais (triagem_id, dispositivo_id, pas, pad, fc, origem, experimental) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (triagem_id, _id_dispositivo(cur, medidor["id"] if pressao_sensor and medidor else None),
             round(vitais["pas"]), round(vitais["pad"]), round(vitais["fc"]),
             "SENSOR" if pressao_sensor else "MANUAL", bool(registro.get("pressao_experimental"))))
        cur.execute(
            "INSERT INTO leitura_sinais_vitais (triagem_id, dispositivo_id, spo2, temperatura, origem, experimental) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (triagem_id, _id_dispositivo(cur, ID_RELOGIO if spo2_sensor else None), round(vitais["spo2"]),
             vitais["temp"], "SENSOR" if spo2_sensor else "MANUAL", bool(registro.get("spo2_experimental"))))

        cur.execute(
            "INSERT INTO classificacao_risco (triagem_id, cor, nivel, tempo_alvo_min, motivo, achados_secundarios, "
            "news2, atendimento_prioritario) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (triagem_id, resultado["cor"], resultado["nivel"], resultado["tempo_alvo_min"], resultado["motivo"][:500],
             json.dumps(resultado.get("outros_achados") or [], ensure_ascii=False), resultado["news2"]["total"],
             resultado.get("atendimento_prioritario", False)))
    log.info("Triagem %s gravada no banco (%s)", triagem_id, resultado["cor"])
    return triagem_id


def salvar_cancelamento(paciente: dict[str, Any], perfil: dict[str, Any], motivo: str) -> int:
    """Triagem cancelada pela câmera (outra pessoa ficou no lugar de quem começou)."""
    with _transacao() as cur:
        paciente_id = _salvar_paciente(cur, paciente, perfil)
        cur.execute(
            "INSERT INTO triagem (paciente_id, status, deficiencias, motivo_cancelamento) "
            "VALUES (%s, 'CANCELADA', %s, %s)",
            (paciente_id, ",".join(perfil.get("deficiencias") or []) or None, motivo[:500]))
        return cur.lastrowid


def salvar_encaminhamento(paciente: dict[str, Any], perfil: dict[str, Any], motivos: list[str]) -> int:
    """Pessoa que não consegue usar o totem sozinha: triagem ENCAMINHADA, sem classificação."""
    with _transacao() as cur:
        paciente_id = _salvar_paciente(cur, paciente, perfil)
        cur.execute(
            "INSERT INTO triagem (paciente_id, status, deficiencias, motivo_encaminhamento) "
            "VALUES (%s, 'ENCAMINHADA', %s, %s)",
            (paciente_id, ",".join(perfil.get("deficiencias") or []) or None, "; ".join(motivos) or None))
        return cur.lastrowid


# --------------------------------------------------------------------------- #
# Consulta (tela de configuração)
# --------------------------------------------------------------------------- #

def estado() -> dict[str, Any]:
    base = {"banco": config.DB_NOME, "servidor": f"{config.DB_HOST}:{config.DB_PORTA}"}
    if not _pronto and not inicializar(forcar=True):  # botão "Atualizar" da tela tenta na hora
        return {**base, "conectado": False, "erro": _ultimo_erro, "total_triagens": None}
    try:
        with _transacao() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM triagem")
            total = cur.fetchone()["n"]
    except Exception as exc:  # noqa: BLE001
        return {**base, "conectado": False, "erro": str(exc), "total_triagens": None}
    return {**base, "conectado": True, "erro": None, "total_triagens": total}


def ultimas_triagens(limite: int = 10) -> list[dict[str, Any]]:
    with _transacao() as cur:
        cur.execute(
            "SELECT t.id, t.data_hora_inicio, t.status, t.modo_questionario, p.nome AS paciente, "
            "c.cor, c.nivel, c.motivo FROM triagem t JOIN paciente p ON p.id = t.paciente_id "
            "LEFT JOIN classificacao_risco c ON c.triagem_id = t.id ORDER BY t.id DESC LIMIT %s", (limite,))
        linhas = cur.fetchall()
    for l in linhas:
        l["data_hora_inicio"] = l["data_hora_inicio"].isoformat(timespec="seconds")
    return linhas


# --------------------------------------------------------------------------- #
# Usuários (login da tela de configuração, autenticacao.py)
# --------------------------------------------------------------------------- #

def buscar_usuario(email: str) -> dict[str, Any] | None:
    with _transacao() as cur:
        cur.execute("SELECT id, nome, email, senha_hash, perfil, ativo, tentativas_invalidas "
                    "FROM usuario WHERE email = %s", (email.strip().lower(),))
        return cur.fetchone()


def registrar_tentativa_invalida(id_usuario: int, maximo: int) -> bool:
    """Soma uma senha errada; ao chegar no máximo, desativa o usuário. Devolve True se bloqueou."""
    with _transacao() as cur:
        cur.execute("UPDATE usuario SET tentativas_invalidas = tentativas_invalidas + 1, "
                    "ativo = IF(tentativas_invalidas >= %s, FALSE, ativo) WHERE id = %s", (maximo, id_usuario))
        cur.execute("SELECT ativo FROM usuario WHERE id = %s", (id_usuario,))
        return not cur.fetchone()["ativo"]


def zerar_tentativas(id_usuario: int) -> None:
    with _transacao() as cur:
        cur.execute("UPDATE usuario SET tentativas_invalidas = 0 WHERE id = %s", (id_usuario,))


def salvar_usuario(nome: str, email: str, senha_hash: str, perfil: str) -> int:
    """Cria o usuário ou, se o e-mail já existe, troca nome, senha e perfil e o desbloqueia."""
    with _transacao() as cur:
        cur.execute(
            "INSERT INTO usuario (nome, email, senha_hash, perfil) VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id), nome = VALUES(nome), senha_hash = VALUES(senha_hash), "
            "perfil = VALUES(perfil), ativo = TRUE, tentativas_invalidas = 0",
            (nome.strip(), email.strip().lower(), senha_hash, perfil))
        return cur.lastrowid


class EmailEmUso(ValueError):
    pass


def listar_usuarios() -> list[dict[str, Any]]:
    with _transacao() as cur:
        cur.execute("SELECT id, nome, email, perfil, ativo, tentativas_invalidas, criado_em "
                    "FROM usuario ORDER BY nome")
        linhas = cur.fetchall()
    for l in linhas:
        l["ativo"] = bool(l["ativo"])
        l["criado_em"] = l["criado_em"].isoformat(timespec="seconds")
    return linhas


def criar_usuario(nome: str, email: str, senha_hash: str, perfil: str) -> int:
    """Cadastro pela tela de configuração: não sobrescreve um e-mail que já existe."""
    try:
        with _transacao() as cur:
            cur.execute("INSERT INTO usuario (nome, email, senha_hash, perfil) VALUES (%s, %s, %s, %s)",
                        (nome.strip(), email.strip().lower(), senha_hash, perfil))
            return cur.lastrowid
    except pymysql.err.IntegrityError as exc:
        raise EmailEmUso("Já existe um usuário com este e-mail.") from exc


def buscar_usuario_por_id(id_usuario: int) -> dict[str, Any] | None:
    with _transacao() as cur:
        cur.execute("SELECT id, nome, email, perfil, ativo FROM usuario WHERE id = %s", (id_usuario,))
        return cur.fetchone()


def contar_admins_ativos() -> int:
    with _transacao() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM usuario WHERE perfil = 'ADMIN' AND ativo = TRUE")
        return cur.fetchone()["n"]


def definir_ativo(id_usuario: int, ativo: bool) -> None:
    """Bloqueia (ativo = False) ou desbloqueia; desbloquear zera as senhas erradas."""
    with _transacao() as cur:
        cur.execute("UPDATE usuario SET ativo = %s, tentativas_invalidas = IF(%s, 0, tentativas_invalidas) "
                    "WHERE id = %s", (ativo, ativo, id_usuario))
