"""
Teste manual da árvore de decisão.

Você digita os sinais vitais (como se viessem dos sensores) e marca os sintomas
(como se viessem da conversa com a LLM). A árvore devolve a classificação.

Como rodar:   python teste_manual.py
"""

import json
import os
import sys

from arvore_decisao import CATALOGO, SINTOMAS, LIMITES, DadosInvalidos, classificar_risco

# Habilita cores no terminal do Windows
if os.name == "nt":
    os.system("")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CORES_ANSI = {
    "VERMELHO": "\033[41;97m", "LARANJA": "\033[48;5;208;97m", "AMARELO": "\033[43;30m",
    "VERDE": "\033[42;97m", "AZUL": "\033[44;97m",
}
RESET = "\033[0m"

CAMPOS = [
    ("pas", "Pressão sistólica (PAS, mmHg)", "Omron"),
    ("pad", "Pressão diastólica (PAD, mmHg)", "Omron"),
    ("fc", "Frequência cardíaca (bpm)", "Omron/relógio"),
    ("spo2", "Saturação de oxigênio (SpO2, %)", "relógio"),
    ("temp", "Temperatura (°C)", "sensor"),
]


def ler_numero(campo, rotulo, origem):
    mn, mx = LIMITES[campo]
    while True:
        txt = input(f"  {rotulo} [{origem}] ({mn}–{mx}): ").strip().replace(",", ".")
        try:
            valor = float(txt)
        except ValueError:
            print("    -> Digite um número.")
            continue
        if not (mn <= valor <= mx):
            print(f"    -> Fora da faixa aceita ({mn} a {mx}).")
            continue
        return valor


def ler_sintomas():
    chaves = list(SINTOMAS)
    print("\nSINTOMAS (o que o usuário está sentindo)")
    i = 0
    for categoria, itens in CATALOGO.items():
        print(f"\n  [{categoria}]")
        for chave, rotulo, descricao, cor in itens:
            i += 1
            print(f"  {i:3}. {rotulo} — {descricao}" + (f"  ({cor.lower()})" if cor else ""))
    while True:
        txt = input("  Números separados por vírgula (Enter = nenhum): ").strip()
        if not txt:
            return []
        try:
            idx = [int(x) for x in txt.replace(" ", "").split(",") if x]
            if all(1 <= i <= len(chaves) for i in idx):
                return [chaves[i - 1] for i in dict.fromkeys(idx)]
        except ValueError:
            pass
        print(f"    -> Use números de 1 a {len(chaves)}, ex.: 2,5")


def mostrar(r):
    cor = r["cor"]
    print("\n" + "=" * 60)
    print(f"  CLASSIFICAÇÃO: {CORES_ANSI[cor]}  {cor} – {r['prioridade']}  {RESET}")
    print("=" * 60)
    print(f"  Nível da árvore : {r['nivel']}")
    print(f"  Motivo          : {r['motivo']}")
    for a in r["outros_achados"]:
        print(f"  Também disparou : [{a['cor']}/{a['nivel']}] {a['motivo']}")
    print(f"  Tempo-alvo      : {r['tempo_alvo_min']} min")
    print(f"  Orientação      : {r['orientacao']}")
    p = r["news2"]["pontos"]
    print(f"  NEWS2 adaptado  : {r['news2']['total']} "
          f"(FC {p['fc']} + PAS {p['pas']} + SpO2 {p['spo2']} + Temp {p['temp']})")
    print("=" * 60)


def main():
    print("=" * 60)
    print("  TESTE MANUAL – ÁRVORE DE DECISÃO (Triagem TCC 2026)")
    print("=" * 60)
    while True:
        print("\nSINAIS VITAIS")
        vitais = {}
        for c, r, o in CAMPOS:
            vitais[c] = ler_numero(c, r, o)
            while c == "pad" and vitais["pad"] >= vitais["pas"]:
                print("    -> A diastólica (PAD) deve ser menor que a sistólica (PAS).")
                vitais["pad"] = ler_numero(c, r, o)
        sintomas = ler_sintomas()
        try:
            r = classificar_risco(**vitais, sintomas=sintomas)
        except DadosInvalidos as e:
            print(f"\n  ERRO: {e}")
        else:
            mostrar(r)
            if input("\n  Ver o JSON que a LLM receberia? (s/N): ").strip().lower() == "s":
                print(json.dumps(r, ensure_ascii=False, indent=2))
        if input("\nTestar outro paciente? (S/n): ").strip().lower() == "n":
            break


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nEncerrado.")
