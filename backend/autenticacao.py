"""
Login da tela de configuração: só usuários da tabela `usuario` com perfil ADMIN entram.

  verificar_login(email, senha)  confere no banco e devolve um token de sessão
  exigir_admin                   dependência do FastAPI que protege as rotas da configuração
  encerrar(token)                logout
  encerrar_do_usuario(id)        derruba as sessões de quem foi bloqueado
  gerar_hash(senha)              usado pelo ../banco/cadastrar_usuario.py

Senhas: PBKDF2-SHA256 com sal aleatório (biblioteca padrão do Python), guardadas em senha_hash como
"pbkdf2_sha256$iteracoes$sal$hash". Depois de TENTATIVAS_MAXIMAS senhas erradas seguidas, o
usuário é bloqueado (ativo = FALSE); um admin desbloqueia na seção "Usuários" da tela de
configuração (ou pelo cadastrar_usuario.py, se não sobrar admin para entrar).
As sessões ficam em memória: reiniciar o backend exige entrar de novo.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

from fastapi import Header, HTTPException

import banco

PERFIS_ADMIN = ("ADMIN",)
TENTATIVAS_MAXIMAS = 5
DURACAO_SESSAO_S = 8 * 3600
ITERACOES = 310_000

_sessoes: dict[str, dict] = {}
_trava = threading.Lock()


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def _confere(senha: str, guardado: str) -> bool:
    try:
        algoritmo, iteracoes, sal, h = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        calculado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), base64.b64decode(sal), int(iteracoes))
        return hmac.compare_digest(calculado, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def verificar_login(email: str, senha: str) -> dict:
    """Devolve {"token", "nome", "email"} ou levanta PermissionError com a mensagem para a tela."""
    usuario = banco.buscar_usuario(email)
    # mesma mensagem para e-mail inexistente e senha errada (não revela quem está cadastrado)
    invalido = PermissionError("E-mail ou senha incorretos.")
    if usuario is None:
        _confere(senha, gerar_hash("x"))  # gasta o mesmo tempo de uma conferência de verdade
        raise invalido
    if not usuario["ativo"]:
        raise PermissionError("Usuário bloqueado ou desativado. Procure o administrador do sistema.")
    if not _confere(senha, usuario["senha_hash"]):
        bloqueou = banco.registrar_tentativa_invalida(usuario["id"], TENTATIVAS_MAXIMAS)
        if bloqueou:
            raise PermissionError(f"Usuário bloqueado após {TENTATIVAS_MAXIMAS} tentativas erradas.")
        raise invalido
    if usuario["perfil"] not in PERFIS_ADMIN:
        raise PermissionError("Só administradores podem acessar a configuração.")

    banco.zerar_tentativas(usuario["id"])
    token = secrets.token_urlsafe(32)
    with _trava:
        agora = time.time()
        for t in [t for t, s in _sessoes.items() if s["expira"] < agora]:
            del _sessoes[t]
        _sessoes[token] = {"id": usuario["id"], "nome": usuario["nome"], "email": usuario["email"],
                           "expira": agora + DURACAO_SESSAO_S}
    return {"token": token, "nome": usuario["nome"], "email": usuario["email"]}


def encerrar(token: str) -> None:
    with _trava:
        _sessoes.pop(token, None)


def encerrar_do_usuario(id_usuario: int) -> None:
    """Derruba as sessões abertas de um usuário (usado ao bloqueá-lo)."""
    with _trava:
        for t in [t for t, s in _sessoes.items() if s["id"] == id_usuario]:
            del _sessoes[t]


def exigir_admin(authorization: str | None = Header(default=None)) -> dict:
    """Dependência das rotas da configuração: exige o cabeçalho "Authorization: Bearer <token>"."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    with _trava:
        sessao = _sessoes.get(token)
        if sessao and sessao["expira"] < time.time():
            del _sessoes[token]
            sessao = None
    if not sessao:
        raise HTTPException(status_code=401, detail="Entre com um usuário administrador para acessar a configuração.")
    return sessao
