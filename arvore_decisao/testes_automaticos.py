"""
Testes automáticos da árvore de decisão: pacientes fictícios com a cor esperada.

As cores esperadas vêm do protocolo de referência (Protocolo de Classificação de Risco baseado
no Manchester, Aparecida de Goiânia, 2025), não da saída do programa:
  P01-P27: os casos da Tabela X da monografia, recalculados pelo protocolo.
  P28-P80: casos da árvore ampliada (sintomas por sistema, combinações e fatores de risco).
  S01-S38: sinais vitais (Anexos II e III) e seus limites exatos.
  D01-D14: discriminadores dos fluxogramas: dor, consciência, combinações e duração.
  Q01-Q10: perfil do paciente (idade, sexo, deficiências).

Como rodar:   python testes_automaticos.py
"""
import sys
from arvore_decisao import classificar_risco, executar_ferramenta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

N = dict(fc=75, pas=120, pad=80, spo2=98, temp=36.5)  # vitais normais
def V(**kw): d = dict(N); d.update(kw); return d

# (id, por que essa cor, vitais, sintomas, cor esperada, nível esperado)
CASOS = [
    ("P01", "Sem sintomas e vitais normais", V(), [], "AZUL", "N6"),
    ("P02", "Não responde [fluxograma geral]", V(), ["inconsciente"], "VERMELHO", "N1"),
    ("P03", "Déficit neurológico agudo é laranja; PA 150/95 é estágio 1 (sem cor)", V(pas=150, pad=95), ["deficit_neurologico"], "LARANJA", "N4"),
    ("P04", "Dor precordial/intensa é laranja; FC 105 é amarelo", V(fc=105), ["dor_toracica_intensa"], "LARANJA", "N4"),
    ("P05", "Não responde vence a crise hipertensiva", V(pas=200, pad=110), ["inconsciente"], "VERMELHO", "N1"),
    ("P06", "SpO2 < 90% é vermelho (Laranja/Vermelho -> o mais grave)", V(spo2=89), ["falta_de_ar"], "VERMELHO", "N2"),
    ("P07", "PA 85/55 não é hipotensão (< 80/50); FC 120 é amarelo", V(pas=85, pad=55, fc=120), [], "AMARELO", "N2"),
    ("P08", "SpO2 91% é baixa (90-94%): amarelo", V(spo2=91), [], "AMARELO", "N2"),
    ("P09", "SpO2 90% amarelo; PA 190/100 amarelo", V(spo2=90, pas=190, pad=100), [], "AMARELO", "N2"),
    ("P10", "PA 190/110 é hipertensão grave: amarelo; dor no peito moderada: amarelo", V(pas=190, pad=110), ["dor_toracica"], "AMARELO", "N2"),
    ("P11", "Dor de cabeça forte (7-10) é laranja", V(pas=170, pad=125), ["cefaleia_intensa"], "LARANJA", "N4"),
    ("P12", "PA 185/100: hipertensão grave, amarelo", V(pas=185, pad=100), [], "AMARELO", "N2"),
    ("P13", "PA 160/122: amarelo", V(pas=160, pad=122), [], "AMARELO", "N2"),
    ("P14", "PA 179/119: amarelo (estágio 2)", V(pas=179, pad=119), [], "AMARELO", "N2"),
    ("P15", "FC 135, SpO2 93% e 39,5 °C: todos amarelos", V(fc=135, spo2=93, temp=39.5, pas=105), ["febre"], "AMARELO", "N2"),
    ("P16", "FC 125, SpO2 92% e 39,3 °C: amarelo", V(fc=125, spo2=92, temp=39.3, pas=108), ["febre"], "AMARELO", "N2"),
    ("P17", "FC 115 e SpO2 93%: amarelo", V(fc=115, spo2=93, temp=38.4, pas=105), [], "AMARELO", "N2"),
    ("P18", "FC 115 e 38,5 °C: amarelo", V(pas=95, pad=60, fc=115, temp=38.5), ["febre"], "AMARELO", "N2"),
    ("P19", "FC 38: bradicardia grave, vermelho", V(fc=38), [], "VERMELHO", "N2"),
    ("P20", "34,8 °C: hipotermia leve (34-36), verde", V(temp=34.8), [], "VERDE", "N2"),
    ("P21", "Dor no peito moderada: amarelo", V(), ["dor_toracica"], "AMARELO", "N4"),
    ("P22", "SpO2 94% amarelo; falta de ar com SpO2 >= 92% amarelo", V(spo2=94), ["falta_de_ar"], "AMARELO", "N2"),
    ("P23", "FC 112: amarelo", V(fc=112, spo2=95, temp=38.2), ["febre"], "AMARELO", "N2"),
    ("P24", "39,4 °C: quente, amarelo", V(temp=39.4, fc=100), ["febre"], "AMARELO", "N2"),
    ("P25", "38,3 °C: febrícula, verde", V(temp=38.3), ["febre"], "VERDE", "N2"),
    ("P26", "Dor moderada (4-6): amarelo", V(), ["dor_moderada"], "AMARELO", "N4"),
    ("P27", "FC 95 é normal", V(fc=95), [], "AZUL", "N6"),
    ("P28", "Convulsão ativa", V(), ["convulsao"], "VERMELHO", "N1"),
    ("P29", "Obstrução de vias aéreas", V(), ["engasgo"], "VERMELHO", "N1"),
    ("P30", "Edema de língua com obstrução", V(), ["inchaco_garganta"], "VERMELHO", "N1"),
    ("P31", "Hemorragia incontrolável", V(fc=100), ["sangramento_intenso"], "VERMELHO", "N1"),
    ("P32", "Choque anafilático: alergia + falta de ar", V(), ["alergia_pele", "falta_de_ar"], "VERMELHO", "N1"),
    ("P33", "Meningismo é laranja; púrpura é verde (sem combinação no protocolo)", V(temp=39.0), ["rigidez_nuca", "manchas_roxas_pele", "febre"], "LARANJA", "N4"),
    ("P34", "41,2 °C: muito quente, laranja", V(temp=41.2), ["febre"], "LARANJA", "N2"),
    ("P35", "Perda súbita da visão é laranja", V(pas=195, pad=105), ["alteracao_visual_subita"], "LARANJA", "N4"),
    ("P36", "Gestante com PA >= 160/110 [exceção obstétrica]", V(pas=165, pad=105), ["gestante"], "VERMELHO", "N3"),
    ("P37", "PA 185/100 amarelo; tontura verde", V(pas=185, pad=100), ["tontura"], "AMARELO", "N2"),
    ("P38", "FC 115 e 38,5 °C: amarelo", V(pas=95, pad=60, fc=115, temp=38.5), ["palpitacao"], "AMARELO", "N2"),
    ("P39", "Hipotermia leve e sensação de desmaio: verde", V(temp=34.8), ["quase_desmaio"], "VERDE", "N2"),
    ("P40", "Dor intensa (7-10)", V(), ["dor_intensa"], "LARANJA", "N4"),
    ("P41", "Respiração inadequada (não completa a frase)", V(spo2=96), ["falta_de_ar_grave"], "LARANJA", "N4"),
    ("P42", "Hematêmese", V(), ["vomito_com_sangue"], "LARANJA", "N4"),
    ("P43", "Potencial suicida: amarelo", V(), ["pensamento_suicida"], "AMARELO", "N4"),
    ("P44", "História de overdose ou envenenamento", V(), ["intoxicacao"], "LARANJA", "N4"),
    ("P45", "Dor de cabeça súbita (dor intensa)", V(), ["cefaleia_subita"], "LARANJA", "N4"),
    ("P46", "Dor precordial: dor no peito + suor frio", V(), ["dor_toracica", "sudorese_fria"], "LARANJA", "N4"),
    ("P47", "Fator de risco não muda a cor: palpitação é verde", V(), ["cardiopata", "palpitacao"], "VERDE", "N4"),
    ("P48", "SpO2 93% amarelo; falta de ar com SpO2 >= 92%", V(spo2=93), ["falta_de_ar"], "AMARELO", "N2"),
    ("P49", "SpO2 94% amarelo; chiado verde", V(spo2=94), ["doenca_respiratoria_cronica", "chiado_no_peito"], "AMARELO", "N2"),
    ("P50", "Falta de ar (amarelo) com inchaço na perna (verde)", V(), ["inchaco_perna_unilateral", "falta_de_ar"], "AMARELO", "N4"),
    ("P51", "Meningismo é laranja", V(temp=38.6), ["febre", "rigidez_nuca"], "LARANJA", "N4"),
    ("P52", "Imunossupressão não sobe a cor: febrícula verde", V(temp=38.2), ["febre", "imunossuprimido"], "VERDE", "N2"),
    ("P53", "Trauma craniano recente: amarelo", V(), ["trauma_craniano", "anticoagulante"], "AMARELO", "N4"),
    ("P54", "Relato de epistaxe: verde", V(), ["sangramento_nasal", "anticoagulante"], "VERDE", "N4"),
    ("P55", "FC 118 amarelo; fezes pretas (relato) amarelo", V(fc=118), ["fezes_com_sangue"], "AMARELO", "N2"),
    ("P56", "Sangramento vaginal na gestação", V(), ["gestante", "sangramento_vaginal"], "LARANJA", "N4"),
    ("P57", "Pré-eclâmpsia: PA 145/92 + dor de cabeça [exceção obstétrica]", V(pas=145, pad=92), ["gestante", "cefaleia"], "LARANJA", "N3"),
    ("P58", "Vômito é verde; diabetes não sobe a cor", V(), ["diabetico", "sede_excessiva", "vomito"], "VERDE", "N4"),
    ("P59", "FC 140 é amarelo (101-149)", V(fc=140), ["tontura"], "AMARELO", "N2"),
    ("P60", "Palpitação com pulso normal: evento recente, verde", V(), ["palpitacao"], "VERDE", "N4"),
    ("P61", "Trauma craniano recente", V(), ["trauma_craniano"], "AMARELO", "N4"),
    ("P62", "Ataque de pânico", V(fc=98), ["crise_ansiedade"], "AMARELO", "N4"),
    ("P63", "Sangramento vaginal controlável", V(), ["sangramento_vaginal"], "AMARELO", "N4"),
    ("P64", "Suspeita de fratura com dor leve", V(), ["suspeita_fratura"], "VERDE", "N4"),
    ("P65", "Sinais de desidratação", V(), ["vomito", "diarreia", "sinais_desidratacao"], "AMARELO", "N4"),
    ("P66", "38,0 °C febrícula; dor de barriga leve", V(temp=38.0), ["dor_abdominal", "febre"], "VERDE", "N2"),
    ("P67", "Disúria com febre (38,4 °C >= 37,8)", V(temp=38.4), ["dor_ao_urinar"], "AMARELO", "N4"),
    ("P68", "SpO2 95% é normal; febrícula verde", V(spo2=95, temp=38.3), ["febre", "tosse"], "VERDE", "N2"),
    ("P69", "PA 165/100 amarelo", V(pas=165, pad=100), ["cefaleia"], "AMARELO", "N2"),
    ("P70", "Idade não sobe a cor: febrícula verde", V(temp=38.2), ["idoso", "febre"], "VERDE", "N2"),
    ("P71", "Tremores sem discriminador: azul", V(), ["diabetico", "tremores"], "AZUL", "N4"),
    ("P72", "Sintomas gripais: verde", V(), ["tosse", "dor_garganta", "coriza"], "VERDE", "N4"),
    ("P73", "Vômitos e diarreia sem desidratação", V(), ["vomito", "diarreia"], "VERDE", "N4"),
    ("P74", "Disúria sem febre", V(), ["dor_ao_urinar"], "VERDE", "N4"),
    ("P75", "Contusão", V(), ["entorse_contusao"], "VERDE", "N4"),
    ("P76", "PA 165/100 sem sintomas: amarelo", V(pas=165, pad=100), [], "AMARELO", "N2"),
    ("P77", "Coriza recente: verde [Queixas respiratórias]", V(), ["coriza"], "VERDE", "N4"),
    ("P78", "Sintomas ansiosos/depressivos: azul", V(), ["insonia", "tristeza_desanimo"], "AZUL", "N4"),
    ("P79", "Só fatores de risco, sem sintomas", V(), ["idoso", "diabetico"], "AZUL", "N6"),
    ("P80", "Sintoma fora do catálogo: verde (lado seguro)", V(), ["outro_sintoma"], "VERDE", "N4"),
]

# Sinais vitais (Anexos II e III) e seus limites. (id, por quê, vitais, pulso irregular, cor, nível)
CASOS_VITAIS = [
    ("S01", "FC 39: bradicardia grave", V(fc=39), False, "VERMELHO", "N2"),
    ("S02", "FC 40: bradicardia (Amarelo/Laranja -> laranja)", V(fc=40), False, "LARANJA", "N2"),
    ("S03", "FC 59: bradicardia", V(fc=59), False, "LARANJA", "N2"),
    ("S04", "FC 60: normal", V(fc=60), False, "AZUL", "N6"),
    ("S05", "FC 100: normal", V(fc=100), False, "AZUL", "N6"),
    ("S06", "FC 101: taquicardia (Verde/Amarelo -> amarelo)", V(fc=101), False, "AMARELO", "N2"),
    ("S07", "FC 149: taquicardia", V(fc=149), False, "AMARELO", "N2"),
    ("S08", "FC 150: taquicardia > 150, laranja", V(fc=150), False, "LARANJA", "N2"),
    ("S09", "Ritmo irregular avisado pelo Omron", V(), True, "LARANJA", "N2"),
    ("S10", "SpO2 89%: muito baixa (Laranja/Vermelho -> vermelho)", V(spo2=89), False, "VERMELHO", "N2"),
    ("S11", "SpO2 90%: baixa (Verde/Amarelo -> amarelo)", V(spo2=90), False, "AMARELO", "N2"),
    ("S12", "SpO2 94%: baixa", V(spo2=94), False, "AMARELO", "N2"),
    ("S13", "SpO2 95%: normal", V(spo2=95), False, "AZUL", "N6"),
    ("S14", "PA 79/50: hipotensão (PAS < 80)", V(pas=79, pad=50), False, "LARANJA", "N2"),
    ("S15", "PA 110/49: hipotensão (PAD < 50)", V(pas=110, pad=49), False, "LARANJA", "N2"),
    ("S16", "PA 80/50: no limite, não é hipotensão", V(pas=80, pad=50), False, "AZUL", "N6"),
    ("S17", "PA 159/99: estágio 1, sem cor", V(pas=159, pad=99), False, "AZUL", "N6"),
    ("S18", "PA 160/90: estágio 2, amarelo", V(pas=160, pad=90), False, "AMARELO", "N2"),
    ("S19", "PA 140/100: estágio 2 pela diastólica", V(pas=140, pad=100), False, "AMARELO", "N2"),
    ("S20", "PA 199/110: estágio 3, amarelo", V(pas=199, pad=110), False, "AMARELO", "N2"),
    ("S21", "PA 200/110: crise hipertensiva (Amarelo/Laranja -> laranja)", V(pas=200, pad=110), False, "LARANJA", "N2"),
    ("S22", "41 °C: muito quente", V(temp=41), False, "LARANJA", "N2"),
    ("S23", "40,9 °C: quente", V(temp=40.9), False, "AMARELO", "N2"),
    ("S24", "38,5 °C: quente", V(temp=38.5), False, "AMARELO", "N2"),
    ("S25", "38,4 °C: febrícula", V(temp=38.4), False, "VERDE", "N2"),
    ("S26", "37,5 °C: febrícula", V(temp=37.5), False, "VERDE", "N2"),
    ("S27", "37,4 °C: normal", V(temp=37.4), False, "AZUL", "N6"),
    ("S28", "36,1 °C: normal", V(temp=36.1), False, "AZUL", "N6"),
    ("S29", "36,0 °C: hipotermia leve (Azul/Verde -> verde)", V(temp=36.0), False, "VERDE", "N2"),
    ("S30", "34,1 °C: hipotermia leve", V(temp=34.1), False, "VERDE", "N2"),
    ("S31", "34,0 °C: hipotermia moderada, vermelho", V(temp=34.0), False, "VERMELHO", "N2"),
    ("S32", "Choque: PAS 80 com FC 140", V(pas=80, pad=50, fc=140), False, "VERMELHO", "N1"),
    ("S33", "Choque: PAS 80 com FC 40", V(pas=80, pad=50, fc=40), False, "VERMELHO", "N1"),
    ("S34", "PAS 78 sem sinal de choque: só hipotensão", V(pas=78, pad=45, fc=100), False, "LARANJA", "N2"),
    ("S35", "PAS 81 com FC 145: não é choque (taquicardia amarela)", V(pas=81, pad=50, fc=145), False, "AMARELO", "N2"),
    ("S36", "Hipotensão com ritmo irregular: laranja (o protocolo não chama de choque)", V(pas=75, pad=45), True, "LARANJA", "N2"),
    ("S37", "Vários vitais: vale o mais grave (SpO2 89%)", V(spo2=89, fc=120, temp=39), False, "VERMELHO", "N2"),
    ("S38", "Tudo normal", V(), False, "AZUL", "N6"),
]

# Discriminadores dos fluxogramas: dor, consciência, combinações e duração.
CASOS_FLUXOGRAMAS = [
    ("D01", "Dor de barriga com nota 5: dor moderada", V(), ["dor_abdominal", "dor_moderada"], "AMARELO", "N4"),
    ("D02", "Dor nas costas com nota 8: dor intensa", V(), ["dor_costas", "dor_intensa"], "LARANJA", "N4"),
    ("D03", "Dor nas costas com nota 2: dor leve", V(), ["dor_costas", "dor_leve"], "VERDE", "N4"),
    ("D04", "Confusão súbita: alteração da consciência", V(), ["confusao_mental"], "LARANJA", "N4"),
    ("D05", "Desmaiou e voltou: história de inconsciência", V(), ["desmaio_recente"], "AMARELO", "N4"),
    ("D06", "Convulsão há menos de 12h e alerta", V(), ["convulsao_recente"], "AMARELO", "N4"),
    ("D07", "Falta de ar com SpO2 91% (< 92%): laranja", V(spo2=91), ["falta_de_ar"], "LARANJA", "N4"),
    ("D08", "Falta de ar com SpO2 92%: amarelo", V(spo2=92), ["falta_de_ar"], "AMARELO", "N2"),
    ("D09", "Dor de garganta com febre relatada", V(), ["dor_garganta", "febre"], "AMARELO", "N4"),
    ("D10", "Dor de garganta com 37,7 °C: sem febre (< 37,8)", V(temp=37.7), ["dor_garganta"], "VERDE", "N2"),
    ("D11", "Coriza há mais de 7 dias: azul", V(), ["coriza", "queixa_antiga"], "AZUL", "N5"),
    ("D12", "Dor moderada há mais de 7 dias continua amarela", V(), ["dor_costas", "dor_moderada", "queixa_antiga"], "AMARELO", "N4"),
    ("D13", "Febrícula há mais de 7 dias: azul", V(temp=38.0), ["febre", "queixa_antiga"], "AZUL", "N5"),
    ("D14", "Choque anafilático: alergia com chiado", V(), ["alergia_pele", "chiado_no_peito"], "VERMELHO", "N1"),
]

# Perfil do paciente (idade, sexo, deficiências), vindo da identificação no totem.
# (id, objetivo, vitais, sintomas, perfil, cor, nível, atendimento prioritário esperado)
CASOS_PERFIL = [
    ("Q01", "70 anos com febrícula: verde, com prioridade legal", V(temp=38.2), ["febre"],
     dict(idade=70), "VERDE", "N2", True),
    ("Q02", "64 anos: prioridade legal (60+)", V(temp=38.2), ["febre"],
     dict(idade=64), "VERDE", "N2", True),
    ("Q03", "40 anos: sem prioridade", V(temp=38.2), ["febre"],
     dict(idade=40), "VERDE", "N2", False),
    ("Q04", "Masculino: 'gestante' é ignorado", V(), ["gestante", "dor_abdominal"],
     dict(idade=30, sexo="M"), "VERDE", "N4", False),
    ("Q05", "Gestante com dor de barriga [exceção obstétrica]", V(), ["gestante", "dor_abdominal"],
     dict(idade=30, sexo="F"), "LARANJA", "N3", True),
    ("Q06", "Masculino: sangramento vaginal é ignorado", V(), ["sangramento_vaginal"],
     dict(sexo="M"), "AZUL", "N6", False),
    ("Q07", "Feminino: dor testicular é ignorada", V(), ["dor_testicular_subita"],
     dict(sexo="F"), "AZUL", "N6", False),
    ("Q08", "Deficiência não muda a cor, só dá prioridade", V(), ["coriza"],
     dict(deficiencias=["visual"]), "VERDE", "N4", True),
    ("Q09", "Deficiência com palpitação", V(), ["palpitacao"],
     dict(deficiencias=["fisica", "auditiva"]), "VERDE", "N4", True),
    ("Q10", "Criança: limites de adulto, com aviso para a enfermagem", V(fc=115), ["febre"],
     dict(idade=8), "AMARELO", "N2", False),
]


def main():
    falhas = 0

    def conferir(cid, obj, r, esp_cor, esp_niv, extra=""):
        nonlocal falhas
        ok = r["cor"] == esp_cor and r["nivel"] == esp_niv
        falhas += not ok
        print(f"{'OK   ' if ok else 'FALHA'} {cid}  esperado {esp_cor:8}/{esp_niv}  obtido {r['cor']:8}/{r['nivel']}"
              f"{extra}  | {obj if ok else r['motivo']}")
        return ok

    for cid, obj, v, sint, esp_cor, esp_niv in CASOS + CASOS_FLUXOGRAMAS:
        conferir(cid, obj, classificar_risco(**v, sintomas=sint), esp_cor, esp_niv)

    for cid, obj, v, irregular, esp_cor, esp_niv in CASOS_VITAIS:
        conferir(cid, obj, classificar_risco(**v, sintomas=[], pulso_irregular=irregular), esp_cor, esp_niv)

    for cid, obj, v, sint, perfil, esp_cor, esp_niv, esp_prio in CASOS_PERFIL:
        r = classificar_risco(**v, sintomas=sint, **perfil)
        prio = "prioritário" if r["atendimento_prioritario"] else "comum"
        if conferir(cid, obj, r, esp_cor, esp_niv, f" ({prio})") and r["atendimento_prioritario"] != esp_prio:
            falhas += 1
            print(f"FALHA {cid}  prioridade esperada {esp_prio}, obtida {r['atendimento_prioritario']}")

    r = classificar_risco(**V(), sintomas=["febre"], idade=8)
    assert r["observacoes"] and "pediátricos" in r["observacoes"][0], r["observacoes"]
    r = classificar_risco(**V(), sintomas=["gestante"], sexo="M")
    assert "gestante" not in r["dados"]["sintomas"] and r["observacoes"], r
    for errado in (dict(idade=-1), dict(idade=200), dict(sexo="X"), dict(deficiencias=["outra"])):
        assert '"erro"' in executar_ferramenta({**V(), "sintomas": [], **errado}), errado
    print("Perfil do paciente (idade, sexo, deficiências): OK")

    # O NEWS2 continua no resultado só como informação
    r = classificar_risco(**V(fc=135, spo2=93, temp=39.5), sintomas=[])
    assert r["news2"]["informativo"] and r["news2"]["total"] == 7 and r["cor"] == "AMARELO", r
    # Outros achados: a dor precordial (laranja) decide; os demais aparecem em ordem
    r = classificar_risco(**V(), sintomas=["dor_toracica", "sudorese_fria", "febre"])
    assert r["cor"] == "LARANJA" and [a["cor"] for a in r["outros_achados"]] == ["AMARELO", "VERDE"], r["outros_achados"]

    # Teste da interface que a LLM vai usar (JSON de entrada -> JSON de saída)
    resp = executar_ferramenta('{"pas": 300, "pad": 90, "fc": 80, "spo2": 97, "temp": 36.5, "sintomas": []}')
    assert '"cor": "LARANJA"' in resp, resp
    erro = executar_ferramenta({"pas": 120, "pad": 80, "fc": 80, "spo2": 97, "temp": 36.5, "sintomas": ["chave_inexistente"]})
    assert '"erro"' in erro, erro
    erro = executar_ferramenta({"pas": 120, "pad": 80, "fc": 80, "spo2": 140, "temp": 36.5, "sintomas": []})
    assert '"erro"' in erro, erro
    assert '"cor": "LARANJA"' in executar_ferramenta({**V(), "sintomas": [], "pulso_irregular": True})
    assert '"erro"' in executar_ferramenta({**V(), "sintomas": [], "pulso_irregular": "sim"})
    print("Interface da LLM (executar_ferramenta): OK")

    total = len(CASOS) + len(CASOS_VITAIS) + len(CASOS_FLUXOGRAMAS) + len(CASOS_PERFIL)
    print(f"\n{total - falhas}/{total} casos passaram.")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
