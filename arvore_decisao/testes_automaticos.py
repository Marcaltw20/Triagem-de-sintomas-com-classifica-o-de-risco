"""
Testes automáticos da árvore de decisão: 80 pacientes fictícios com a cor esperada.
P01-P27: os mesmos casos da Tabela X da monografia (árvore original).
P28-P80: casos da árvore ampliada (sintomas por sistema, combinações e fatores de risco).

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

# (id, objetivo do caso, vitais, sintomas, cor esperada, nível esperado)
CASOS = [
    ("P01", "Paciente sem alterações", V(), [], "AZUL", "N6"),
    ("P02", "Alarme: confusão aguda", V(), ["inconsciente"], "VERMELHO", "N1"),
    ("P03", "Alarme: déficit neurológico", V(pas=150, pad=95), ["deficit_neurologico"], "VERMELHO", "N1"),
    ("P04", "Alarme: dor torácica intensa", V(fc=105), ["dor_toracica_intensa"], "VERMELHO", "N1"),
    ("P05", "Precedência: alarme antes de crise hipertensiva", V(pas=200, pad=110), ["inconsciente"], "VERMELHO", "N1"),
    ("P06", "Hipoxemia grave", V(spo2=89), ["falta_de_ar"], "VERMELHO", "N2"),
    ("P07", "Hipotensão", V(pas=85, pad=55, fc=120), [], "VERMELHO", "N2"),
    ("P08", "Limite: SpO2 = 91%", V(spo2=91), [], "VERMELHO", "N2"),
    ("P09", "Precedência: vital crítico antes de crise hipertensiva", V(spo2=90, pas=190, pad=100), [], "VERMELHO", "N2"),
    ("P10", "Emergência hipertensiva (PAS)", V(pas=190, pad=110), ["dor_toracica"], "VERMELHO", "N3"),
    ("P11", "Emergência hipertensiva (PAD)", V(pas=170, pad=125), ["cefaleia_intensa"], "VERMELHO", "N3"),
    ("P12", "Urgência hipertensiva (PAS)", V(pas=185, pad=100), [], "LARANJA", "N3"),
    ("P13", "Urgência hipertensiva (PAD)", V(pas=160, pad=122), [], "LARANJA", "N3"),
    ("P14", "Limite: PAS 179 / PAD 119 sem sintomas", V(pas=179, pad=119), [], "AZUL", "N6"),
    ("P15", "NEWS2 alto (8)", V(fc=135, spo2=93, temp=39.5, pas=105), ["febre"], "LARANJA", "N4"),
    ("P16", "Limite: NEWS2 = 7", V(fc=125, spo2=92, temp=39.3, pas=108), ["febre"], "LARANJA", "N4"),
    ("P17", "Limite: NEWS2 = 6", V(fc=115, spo2=93, temp=38.4, pas=105), [], "AMARELO", "N4"),
    ("P18", "Limite: NEWS2 = 5", V(pas=95, pad=60, fc=115, temp=38.5), ["febre"], "AMARELO", "N4"),
    ("P19", "Parâmetro isolado = 3 (bradicardia)", V(fc=38), [], "AMARELO", "N4"),
    ("P20", "Parâmetro isolado = 3 (hipotermia)", V(temp=34.8), [], "AMARELO", "N4"),
    ("P21", "Dor torácica sem alteração de vitais", V(), ["dor_toracica"], "AMARELO", "N5"),
    ("P22", "Falta de ar com SpO2 limítrofe", V(spo2=94), ["falta_de_ar"], "AMARELO", "N5"),
    ("P23", "Limite: NEWS2 = 4", V(fc=112, spo2=95, temp=38.2), ["febre"], "VERDE", "N6"),
    ("P24", "Febre alta isolada (NEWS2 = 3)", V(temp=39.4, fc=100), ["febre"], "VERDE", "N6"),
    ("P25", "Febre baixa", V(temp=38.3), ["febre"], "VERDE", "N6"),
    ("P26", "Dor moderada com vitais normais", V(), ["dor_moderada"], "VERDE", "N6"),
    ("P27", "Taquicardia leve isolada", V(fc=95), [], "VERDE", "N6"),

    # ---- Árvore ampliada: sintomas por sistema, combinações e fatores de risco ----
    # Sinais de alarme (N1)
    ("P28", "Alarme: convulsão", V(), ["convulsao"], "VERMELHO", "N1"),
    ("P29", "Alarme: engasgo", V(), ["engasgo"], "VERMELHO", "N1"),
    ("P30", "Alarme: inchaço de língua/garganta", V(), ["inchaco_garganta"], "VERMELHO", "N1"),
    ("P31", "Alarme: sangramento intenso", V(fc=100), ["sangramento_intenso"], "VERMELHO", "N1"),
    ("P32", "Combinação de alarme: anafilaxia", V(), ["alergia_pele", "falta_de_ar"], "VERMELHO", "N1"),
    ("P33", "Combinação de alarme: meningite com manchas roxas", V(temp=39.0), ["rigidez_nuca", "manchas_roxas_pele", "febre"], "VERMELHO", "N1"),
    # Sinais vitais / pressão (N2, N3)
    ("P34", "Hiperpirexia (41 °C)", V(temp=41.2), ["febre"], "LARANJA", "N2"),
    ("P35", "Emergência hipertensiva com alteração visual", V(pas=195, pad=105), ["alteracao_visual_subita"], "VERMELHO", "N3"),
    ("P36", "Gestante com PA >= 160/110", V(pas=165, pad=105), ["gestante"], "VERMELHO", "N3"),
    ("P37", "Crise hipertensiva com sintoma leve (não é órgão-alvo)", V(pas=185, pad=100), ["tontura"], "LARANJA", "N3"),
    # NEWS2 + sintoma (N4)
    ("P38", "NEWS2 = 5 com sintoma moderado", V(pas=95, pad=60, fc=115, temp=38.5), ["palpitacao"], "LARANJA", "N4"),
    ("P39", "Parâmetro isolado = 3 com sintoma moderado", V(temp=34.8), ["quase_desmaio"], "LARANJA", "N4"),
    # Sintomas muito urgentes (N5)
    ("P40", "Dor intensa", V(), ["dor_intensa"], "LARANJA", "N5"),
    ("P41", "Falta de ar grave", V(spo2=96), ["falta_de_ar_grave"], "LARANJA", "N5"),
    ("P42", "Vômito com sangue", V(), ["vomito_com_sangue"], "LARANJA", "N5"),
    ("P43", "Pensamento suicida", V(), ["pensamento_suicida"], "LARANJA", "N5"),
    ("P44", "Intoxicação", V(), ["intoxicacao"], "LARANJA", "N5"),
    ("P45", "Dor de cabeça súbita", V(), ["cefaleia_subita"], "LARANJA", "N5"),
    # Combinações muito urgentes (N5)
    ("P46", "Dor no peito + suor frio", V(), ["dor_toracica", "sudorese_fria"], "LARANJA", "N5"),
    ("P47", "Cardiopata com palpitação", V(), ["cardiopata", "palpitacao"], "LARANJA", "N5"),
    ("P48", "Falta de ar com SpO2 = 93%", V(spo2=93), ["falta_de_ar"], "LARANJA", "N5"),
    ("P49", "Asmático com chiado e SpO2 = 94%", V(spo2=94), ["doenca_respiratoria_cronica", "chiado_no_peito"], "LARANJA", "N5"),
    ("P50", "Inchaço em uma perna + falta de ar", V(), ["inchaco_perna_unilateral", "falta_de_ar"], "LARANJA", "N5"),
    ("P51", "Febre + rigidez de nuca", V(temp=38.6), ["febre", "rigidez_nuca"], "LARANJA", "N5"),
    ("P52", "Febre em imunossuprimido", V(temp=38.2), ["febre", "imunossuprimido"], "LARANJA", "N5"),
    ("P53", "Pancada na cabeça em uso de anticoagulante", V(), ["trauma_craniano", "anticoagulante"], "LARANJA", "N5"),
    ("P54", "Sangramento nasal em uso de anticoagulante", V(), ["sangramento_nasal", "anticoagulante"], "LARANJA", "N5"),
    ("P55", "Sangue nas fezes com taquicardia", V(fc=118), ["fezes_com_sangue"], "LARANJA", "N5"),
    ("P56", "Gestante com sangramento", V(), ["gestante", "sangramento_vaginal"], "LARANJA", "N5"),
    ("P57", "Pré-eclâmpsia: gestante, PA 145/92, dor de cabeça", V(pas=145, pad=92), ["gestante", "cefaleia"], "LARANJA", "N5"),
    ("P58", "Diabético com sede excessiva e vômito", V(), ["diabetico", "sede_excessiva", "vomito"], "LARANJA", "N5"),
    ("P59", "Taquicardia >= 131 com tontura", V(fc=140), ["tontura"], "LARANJA", "N5"),
    # Sintomas moderados (N5)
    ("P60", "Palpitação isolada", V(), ["palpitacao"], "AMARELO", "N5"),
    ("P61", "Pancada na cabeça sem agravantes", V(), ["trauma_craniano"], "AMARELO", "N5"),
    ("P62", "Crise de ansiedade", V(fc=98), ["crise_ansiedade"], "AMARELO", "N5"),
    ("P63", "Sangramento vaginal (não gestante)", V(), ["sangramento_vaginal"], "AMARELO", "N5"),
    ("P64", "Suspeita de fratura", V(), ["suspeita_fratura"], "AMARELO", "N5"),
    # Combinações moderadas (N5)
    ("P65", "Vômito e diarreia com desidratação", V(), ["vomito", "diarreia", "sinais_desidratacao"], "AMARELO", "N5"),
    ("P66", "Dor abdominal com febre", V(temp=38.0), ["dor_abdominal", "febre"], "AMARELO", "N5"),
    ("P67", "Dor ao urinar com febre medida", V(temp=38.4), ["dor_ao_urinar"], "AMARELO", "N5"),
    ("P68", "Febre e tosse com SpO2 = 95%", V(spo2=95, temp=38.3), ["febre", "tosse"], "AMARELO", "N5"),
    ("P69", "PA 165/100 com dor de cabeça", V(pas=165, pad=100), ["cefaleia"], "AMARELO", "N5"),
    ("P70", "Idoso com febre", V(temp=38.2), ["idoso", "febre"], "AMARELO", "N5"),
    ("P71", "Diabético com tremores", V(), ["diabetico", "tremores"], "AMARELO", "N5"),
    # Leves e mínimos (N6)
    ("P72", "Gripe: tosse, dor de garganta e coriza", V(), ["tosse", "dor_garganta", "coriza"], "VERDE", "N6"),
    ("P73", "Vômito e diarreia sem desidratação", V(), ["vomito", "diarreia"], "VERDE", "N6"),
    ("P74", "Dor ao urinar sem febre", V(), ["dor_ao_urinar"], "VERDE", "N6"),
    ("P75", "Torção no tornozelo", V(), ["entorse_contusao"], "VERDE", "N6"),
    ("P76", "PA 165/100 sem sintomas", V(pas=165, pad=100), [], "AZUL", "N6"),
    ("P77", "Queixa mínima: coriza", V(), ["coriza"], "AZUL", "N6"),
    ("P78", "Queixa mínima: insônia e tristeza", V(), ["insonia", "tristeza_desanimo"], "AZUL", "N6"),
    ("P79", "Só fator de risco, sem sintomas", V(), ["idoso", "diabetico"], "AZUL", "N6"),
    ("P80", "Sintoma fora do catálogo", V(), ["outro_sintoma"], "VERDE", "N6"),
]

# Perfil do paciente (idade, sexo, deficiências), vindo da identificação no totem.
# (id, objetivo, vitais, sintomas, perfil, cor, nível, atendimento prioritário esperado)
CASOS_PERFIL = [
    ("Q01", "70 anos com febre: 'idoso' entra sozinho", V(temp=38.2), ["febre"],
     dict(idade=70), "AMARELO", "N5", True),
    ("Q02", "64 anos com febre: ainda não é fator de risco, mas tem prioridade legal", V(temp=38.2), ["febre"],
     dict(idade=64), "VERDE", "N6", True),
    ("Q03", "40 anos com febre: sem agravante e sem prioridade", V(temp=38.2), ["febre"],
     dict(idade=40), "VERDE", "N6", False),
    ("Q04", "Masculino: 'gestante' é ignorado", V(), ["gestante", "dor_abdominal"],
     dict(idade=30, sexo="M"), "VERDE", "N6", False),
    ("Q05", "Feminino: gestante com dor abdominal continua laranja", V(), ["gestante", "dor_abdominal"],
     dict(idade=30, sexo="F"), "LARANJA", "N5", True),
    ("Q06", "Masculino: sangramento vaginal é ignorado", V(), ["sangramento_vaginal"],
     dict(sexo="M"), "AZUL", "N6", False),
    ("Q07", "Feminino: dor testicular é ignorada", V(), ["dor_testicular_subita"],
     dict(sexo="F"), "AZUL", "N6", False),
    ("Q08", "Deficiência não muda a cor, só dá prioridade", V(), ["coriza"],
     dict(deficiencias=["visual"]), "AZUL", "N6", True),
    ("Q09", "Deficiência com sintoma moderado", V(), ["palpitacao"],
     dict(deficiencias=["fisica", "auditiva"]), "AMARELO", "N5", True),
    ("Q10", "Criança: cor mantida, com aviso sobre o NEWS2", V(fc=115), ["febre"],
     dict(idade=8), "VERDE", "N6", False),
]


def main():
    falhas = 0
    for cid, obj, v, sint, esp_cor, esp_niv in CASOS:
        r = classificar_risco(**v, sintomas=sint)
        ok = r["cor"] == esp_cor and r["nivel"] == esp_niv
        falhas += not ok
        print(f"{'OK   ' if ok else 'FALHA'} {cid}  esperado {esp_cor:8}/{esp_niv}  obtido {r['cor']:8}/{r['nivel']}  | {r['motivo']}")

    for cid, obj, v, sint, perfil, esp_cor, esp_niv, esp_prio in CASOS_PERFIL:
        r = classificar_risco(**v, sintomas=sint, **perfil)
        ok = r["cor"] == esp_cor and r["nivel"] == esp_niv and r["atendimento_prioritario"] == esp_prio
        falhas += not ok
        prio = "prioritário" if r["atendimento_prioritario"] else "comum"
        print(f"{'OK   ' if ok else 'FALHA'} {cid}  esperado {esp_cor:8}/{esp_niv}  obtido {r['cor']:8}/{r['nivel']} "
              f"({prio})  | {obj}")

    r = classificar_risco(**V(), sintomas=["febre"], idade=8)
    assert r["observacoes"] and "NEWS2" in r["observacoes"][0], r["observacoes"]
    r = classificar_risco(**V(), sintomas=["gestante"], sexo="M")
    assert "gestante" not in r["dados"]["sintomas"] and r["observacoes"], r
    for errado in (dict(idade=-1), dict(idade=200), dict(sexo="X"), dict(deficiencias=["outra"])):
        assert '"erro"' in executar_ferramenta({**V(), "sintomas": [], **errado}), errado
    print("Perfil do paciente (idade, sexo, deficiências): OK")

    # Teste da interface que a LLM vai usar (JSON de entrada -> JSON de saída)
    resp = executar_ferramenta('{"pas": 300, "pad": 90, "fc": 80, "spo2": 97, "temp": 36.5, "sintomas": []}')
    assert '"cor": "LARANJA"' in resp, resp
    erro = executar_ferramenta({"pas": 120, "pad": 80, "fc": 80, "spo2": 97, "temp": 36.5, "sintomas": ["chave_inexistente"]})
    assert '"erro"' in erro, erro
    r = classificar_risco(**V(), sintomas=["dor_toracica", "sudorese_fria", "febre"])
    assert [a["cor"] for a in r["outros_achados"]] == ["AMARELO", "VERDE"], r["outros_achados"]
    erro = executar_ferramenta({"pas": 120, "pad": 80, "fc": 80, "spo2": 140, "temp": 36.5, "sintomas": []})
    assert '"erro"' in erro, erro
    print("Interface da LLM (executar_ferramenta): OK")

    total = len(CASOS) + len(CASOS_PERFIL)
    print(f"\n{total - falhas}/{total} casos passaram.")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
