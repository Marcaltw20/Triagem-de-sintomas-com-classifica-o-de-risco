"""
Cadastra (ou atualiza) um usuário na tabela `usuario` do banco da triagem.

Só usuários com perfil ADMIN entram na tela de configuração do totem.

Uso (com o MySQL do XAMPP ligado), dentro da pasta banco:
    python cadastrar_usuario.py                 -> pergunta nome, e-mail e senha; perfil ADMIN
    python cadastrar_usuario.py --perfil GESTOR  -> outro perfil (ATENDENTE, GESTOR ou ADMIN)

Se o e-mail já existir, troca nome, senha e perfil e desbloqueia o usuário (serve também para
"esqueci a senha" e para desbloquear depois de 5 senhas erradas).
A senha é digitada sem aparecer na tela e só o hash (PBKDF2) vai para o banco.
"""
from __future__ import annotations

import argparse
import getpass
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

import config  # noqa: E402,F401  (carrega o .env)
import autenticacao  # noqa: E402
import banco  # noqa: E402

SENHA_MINIMA = 8


def main() -> int:
    parser = argparse.ArgumentParser(description="Cadastra um usuário da triagem.")
    parser.add_argument("--perfil", choices=["ADMIN", "GESTOR", "ATENDENTE"], default="ADMIN")
    perfil = parser.parse_args().perfil

    if not banco.inicializar(forcar=True):
        print("Não consegui conectar no banco. O MySQL está ligado no XAMPP Control Panel?")
        return 1

    nome = input("Nome: ").strip()
    email = input("E-mail: ").strip().lower()
    if not nome or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print("Nome vazio ou e-mail inválido.")
        return 1
    senha = getpass.getpass(f"Senha (mínimo {SENHA_MINIMA} caracteres): ")
    if len(senha) < SENHA_MINIMA:
        print(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
        return 1
    if getpass.getpass("Repita a senha: ") != senha:
        print("As senhas não conferem.")
        return 1

    id_usuario = banco.salvar_usuario(nome, email, autenticacao.gerar_hash(senha), perfil)
    print(f"Usuário {email} salvo (id {id_usuario}, perfil {perfil}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
