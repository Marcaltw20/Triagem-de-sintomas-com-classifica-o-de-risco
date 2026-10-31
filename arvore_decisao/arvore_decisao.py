"""
Árvore de decisão para classificação de risco — TCC 2026 (Triagem de Sintomas).

Este módulo é o "motor" da classificação. Ele é independente da LLM:
  - chamado pelo teste manual (teste_manual.py);
  - chamado pelo backend da triagem (pasta backend/), que recebe da LLM
    a lista de sintomas e dos sensores os sinais vitais.

A LLM NÃO decide a cor. Ela só transforma o que o usuário disse em chaves de sintomas
e repassa os sinais vitais vindos dos sensores. Quem decide é a árvore.

Entradas
  - 5 sinais vitais (PAS, PAD, FC, SpO2, temperatura);
  - sintomas e fatores de risco relatados (chaves do CATALOGO, organizadas por sistema
    do corpo). Cada sintoma tem uma cor-base (discriminador, como nos fluxogramas de
    Manchester) e pode ser agravado por combinações com outros sintomas, com os sinais
    vitais ou com fatores de risco (gestante, idoso, diabético etc.).

Ordem de avaliação (do mais grave para o mais leve; vale a primeira condição verdadeira):
  VERMELHO
    N1  Sinal de alarme relatado (inconsciência, déficit neurológico, convulsão, ...)
    N1  Combinação de alarme (anafilaxia; meningite com manchas roxas)
    N2  SpO2 <= 91% ou PAS <= 90 mmHg
    N3  PAS >= 180 ou PAD >= 120 + sintoma de lesão de órgão-alvo (emergência hipertensiva)
        Gestante com PAS >= 160 ou PAD >= 110
  LARANJA
    N2  Temperatura >= 41 °C
    N3  PAS >= 180 ou PAD >= 120 sem sintomas (urgência hipertensiva)
    N4  NEWS2 adaptado >= 7
    N4  NEWS2 5-6 (ou parâmetro isolado = 3) + sintoma moderado
    N5  Sintoma muito urgente (dor intensa, falta de ar grave, vômito com sangue, ...)
    N5  Combinação muito urgente (dor torácica + sudorese, febre + rigidez de nuca, ...)
  AMARELO
    N4  NEWS2 adaptado 5-6 ou parâmetro isolado = 3
    N5  Sintoma moderado (dor torácica, falta de ar, cefaleia intensa, palpitação, ...)
    N5  Combinação moderada (vômito + desidratação, febre + dor abdominal, ...)
  VERDE
    N6  NEWS2 >= 1 ou sintoma leve (febre, tosse, dor moderada, ...)
  AZUL
    N6  Queixa mínima (coriza, insônia, ...) ou nenhum sintoma, com sinais vitais normais

Todas as regras que dispararam (não só a que definiu a cor) voltam em `outros_achados`.

Dados do paciente (vêm da identificação no totem, não da conversa)
  - idade: com 65 anos ou mais, o fator de risco "idoso" entra sozinho na árvore;
    abaixo de 16 anos, o resultado avisa que o NEWS2 foi feito para adultos.
  - sexo: no masculino, chaves só possíveis no feminino (gestante, sangramento vaginal...)
    são ignoradas; no feminino, a dor testicular é ignorada.
  - deficiências: não mudam a cor (não deixam o caso mais grave), mas dão direito a
    atendimento prioritário dentro da cor (Lei 10.048/2000), assim como 60 anos ou mais
    e gestação. Deficiência que impede usar o totem sozinho é tratada antes, no próprio
    totem, que encaminha a pessoa direto para a enfermagem.

Referências: Sistema Manchester de Classificação de Risco; NEWS2 (Royal College of
Physicians, 2017); Diretrizes Brasileiras de Hipertensão Arterial (Barroso et al., 2021).
"""

from __future__ import annotations

import json
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# Catálogo de sintomas
# --------------------------------------------------------------------------- #

# categoria -> lista de (chave, rótulo curto, descrição para a LLM, cor-base)
# cor-base None = fator de risco: não classifica sozinho, só agrava outras regras.
CATALOGO: dict[str, list[tuple[str, str, str, str | None]]] = {
    "Fatores de risco": [
        ("gestante", "Gestante", "Está grávida ou pode estar grávida", None),
        ("idoso", "Idoso (65+)", "Tem 65 anos ou mais", None),
        ("diabetico", "Diabético", "Tem diabetes", None),
        ("cardiopata", "Doença do coração", "Tem doença do coração (infarto prévio, insuficiência cardíaca, arritmia, stent)", None),
        ("doenca_respiratoria_cronica", "Asma/DPOC", "Tem asma, bronquite crônica, enfisema ou DPOC", None),
        ("imunossuprimido", "Imunidade baixa", "Faz quimioterapia, é transplantado, vive com HIV ou usa corticoide em dose alta", None),
        ("anticoagulante", "Usa anticoagulante", "Usa remédio para afinar o sangue (varfarina, rivaroxabana, apixabana etc.)", None),
    ],
    "Neurológico": [
        ("inconsciente", "Confusão/desmaio", "Confusão mental, desmaio ou inconsciência", "VERMELHO"),
        ("deficit_neurologico", "Déficit neurológico", "Fraqueza/dormência em um lado do corpo, fala enrolada ou boca torta", "VERMELHO"),
        ("convulsao", "Convulsão", "Convulsão agora ou nas últimas horas", "VERMELHO"),
        ("cefaleia_subita", "Dor de cabeça súbita", "Dor de cabeça que começou de repente, a pior da vida", "LARANJA"),
        ("alteracao_visual_subita", "Alteração visual súbita", "Perda de visão, visão dupla ou muito embaçada que começou de repente", "LARANJA"),
        ("cefaleia_intensa", "Dor de cabeça forte", "Dor de cabeça forte", "AMARELO"),
        ("rigidez_nuca", "Rigidez de nuca", "Pescoço duro, dor ao encostar o queixo no peito", "AMARELO"),
        ("quase_desmaio", "Sensação de desmaio", "Sensação de que vai desmaiar, visão escurecendo", "AMARELO"),
        ("cefaleia", "Dor de cabeça", "Dor de cabeça leve ou moderada", "VERDE"),
        ("tontura", "Tontura", "Tontura ou vertigem (tudo girando)", "VERDE"),
        ("formigamento", "Formigamento", "Formigamento ou dormência em mãos, pés ou rosto (dos dois lados)", "VERDE"),
        ("tremores", "Tremores", "Tremores no corpo ou nas mãos", "VERDE"),
    ],
    "Coração e circulação": [
        ("dor_toracica_intensa", "Dor no peito intensa", "Dor no peito forte (aperto, irradia para braço/mandíbula)", "VERMELHO"),
        ("dor_toracica", "Dor no peito", "Dor ou desconforto no peito (leve/moderado)", "AMARELO"),
        ("palpitacao", "Palpitação", "Coração acelerado, disparado ou batendo fora do ritmo", "AMARELO"),
        ("sudorese_fria", "Suor frio", "Suor frio, pele pálida e pegajosa", "AMARELO"),
        ("inchaco_perna_unilateral", "Inchaço em uma perna", "Uma perna só inchada, dolorida, quente ou vermelha", "AMARELO"),
        ("inchaco_pernas", "Inchaço nas pernas", "Inchaço nas duas pernas ou nos pés", "VERDE"),
    ],
    "Respiratório": [
        ("engasgo", "Engasgo/sufocamento", "Engasgado, sufocando, não consegue respirar ou falar", "VERMELHO"),
        ("labios_roxos", "Lábios roxos", "Lábios, rosto ou pontas dos dedos roxos/azulados", "VERMELHO"),
        ("falta_de_ar_grave", "Falta de ar grave", "Falta de ar em repouso, não consegue completar uma frase", "LARANJA"),
        ("falta_de_ar", "Falta de ar", "Falta de ar", "AMARELO"),
        ("chiado_no_peito", "Chiado no peito", "Chiado no peito, crise de asma", "AMARELO"),
        ("tosse_com_sangue", "Tosse com sangue", "Tosse com sangue", "AMARELO"),
        ("tosse", "Tosse", "Tosse seca ou com catarro", "VERDE"),
        ("dor_garganta", "Dor de garganta", "Dor de garganta, rouquidão", "VERDE"),
        ("coriza", "Coriza/nariz entupido", "Coriza, nariz entupido, espirros", "AZUL"),
    ],
    "Digestivo": [
        ("dor_abdominal_intensa", "Dor de barriga intensa", "Dor na barriga muito forte, barriga dura", "LARANJA"),
        ("vomito_com_sangue", "Vômito com sangue", "Vômito com sangue ou parecendo borra de café", "LARANJA"),
        ("vomito_persistente", "Vômitos persistentes", "Vomita várias vezes, não segura líquidos", "AMARELO"),
        ("fezes_com_sangue", "Sangue nas fezes", "Fezes com sangue ou pretas como piche", "AMARELO"),
        ("ictericia", "Pele/olhos amarelos", "Pele ou olhos amarelados", "AMARELO"),
        ("dor_abdominal", "Dor de barriga", "Dor na barriga ou no estômago (leve/moderada), cólica", "VERDE"),
        ("nausea", "Enjoo", "Enjoo, náusea", "VERDE"),
        ("vomito", "Vômito", "Vomitou poucas vezes", "VERDE"),
        ("diarreia", "Diarreia", "Diarreia", "VERDE"),
        ("azia", "Azia", "Azia, queimação no estômago, refluxo", "VERDE"),
        ("dificuldade_engolir", "Dificuldade para engolir", "Dificuldade ou dor para engolir", "VERDE"),
        ("constipacao", "Prisão de ventre", "Prisão de ventre, gases", "AZUL"),
    ],
    "Urinário e reprodutivo": [
        ("dor_testicular_subita", "Dor testicular súbita", "Dor forte e súbita no testículo", "LARANJA"),
        ("perda_liquido_contracoes", "Contrações/perda de líquido", "Gestante com contrações fortes ou perda de líquido", "LARANJA"),
        ("bebe_mexendo_menos", "Bebê mexendo menos", "Gestante que sente o bebê mexer bem menos ou parar de mexer", "LARANJA"),
        ("sangramento_vaginal", "Sangramento vaginal", "Sangramento vaginal fora da menstruação ou muito maior que o normal", "AMARELO"),
        ("retencao_urinaria", "Não consegue urinar", "Vontade de urinar mas não consegue, bexiga cheia e dolorida", "AMARELO"),
        ("sangue_na_urina", "Sangue na urina", "Urina com sangue", "AMARELO"),
        ("dor_ao_urinar", "Dor ao urinar", "Dor ou ardência ao urinar, urinando toda hora", "VERDE"),
        ("colica_menstrual", "Cólica/dor pélvica", "Cólica menstrual ou dor na parte baixa da barriga", "VERDE"),
        ("corrimento_genital", "Corrimento", "Corrimento, coceira ou ferida na região genital", "VERDE"),
    ],
    "Alergia e pele": [
        ("inchaco_garganta", "Inchaço de língua/garganta", "Língua, lábios ou garganta inchando, dificuldade para respirar ou engolir", "VERMELHO"),
        ("manchas_roxas_pele", "Manchas roxas na pele", "Pintas ou manchas roxas/vermelhas que não somem ao apertar", "AMARELO"),
        ("alergia_pele", "Alergia na pele", "Urticária, placas vermelhas ou coceira pelo corpo", "VERDE"),
        ("erupcao_pele", "Manchas/bolhas na pele", "Manchas, bolhas ou feridas na pele", "VERDE"),
        ("ferida_infectada", "Ferida infectada", "Ferida ou furúnculo vermelho, quente, com pus", "VERDE"),
    ],
    "Trauma e acidentes": [
        ("sangramento_intenso", "Sangramento intenso", "Sangramento forte que não para", "VERMELHO"),
        ("trauma_grave", "Acidente grave", "Acidente de trânsito, queda de altura ou pancada muito forte", "LARANJA"),
        ("fratura_exposta", "Fratura exposta", "Osso aparecendo ou membro muito deformado", "LARANJA"),
        ("queimadura_grave", "Queimadura grave", "Queimadura grande, com bolhas extensas, no rosto ou por eletricidade/química", "LARANJA"),
        ("intoxicacao", "Intoxicação", "Tomou remédio em excesso, veneno, produto de limpeza ou droga", "LARANJA"),
        ("picada_animal_peconhento", "Picada de animal peçonhento", "Picada de cobra, escorpião ou aranha", "LARANJA"),
        ("quimico_no_olho", "Produto químico no olho", "Produto químico caiu no olho", "LARANJA"),
        ("trauma_craniano", "Pancada na cabeça", "Bateu a cabeça", "AMARELO"),
        ("suspeita_fratura", "Suspeita de fratura", "Não consegue mexer ou apoiar o membro depois de queda/pancada", "AMARELO"),
        ("sangramento_moderado", "Sangramento", "Sangramento que diminui ao apertar, mas não para de vez", "AMARELO"),
        ("ferida_profunda", "Corte profundo", "Corte profundo, que precisa de pontos", "AMARELO"),
        ("corte_leve", "Corte/arranhão", "Corte pequeno ou arranhão", "VERDE"),
        ("entorse_contusao", "Torção/pancada", "Torção, pancada ou inchaço em braço, perna, pé ou mão", "VERDE"),
        ("queimadura_leve", "Queimadura leve", "Queimadura pequena", "VERDE"),
        ("mordida_animal", "Mordida de animal", "Mordida ou arranhão de cachorro, gato ou outro animal", "VERDE"),
    ],
    "Olhos, ouvidos, nariz e boca": [
        ("sangramento_nasal", "Sangramento no nariz", "Sangramento pelo nariz", "VERDE"),
        ("dor_olho", "Problema no olho", "Olho vermelho, dolorido, com secreção ou cisco", "VERDE"),
        ("dor_ouvido", "Dor de ouvido", "Dor de ouvido, secreção ou zumbido", "VERDE"),
        ("dor_dente", "Dor de dente", "Dor de dente ou na gengiva", "VERDE"),
    ],
    "Músculos e articulações": [
        ("dor_costas", "Dor nas costas", "Dor nas costas ou na lombar", "VERDE"),
        ("dor_articular", "Dor nas juntas", "Dor em articulações (joelho, ombro, punho etc.)", "VERDE"),
        ("dor_muscular", "Dor no corpo", "Dor muscular, dor no corpo todo", "VERDE"),
    ],
    "Saúde mental": [
        ("pensamento_suicida", "Pensamento suicida", "Pensa em se machucar ou tirar a própria vida", "LARANJA"),
        ("agitacao_agressividade", "Agitação intensa", "Muito agitado, agressivo ou fora de controle", "LARANJA"),
        ("crise_ansiedade", "Crise de ansiedade", "Crise de ansiedade ou pânico, sensação de que vai morrer", "AMARELO"),
        ("alucinacao", "Alucinação", "Vê ou ouve coisas que não existem", "AMARELO"),
        ("tristeza_desanimo", "Tristeza/ansiedade", "Tristeza, desânimo, ansiedade ou estresse sem crise", "AZUL"),
        ("insonia", "Insônia", "Dificuldade para dormir", "AZUL"),
    ],
    "Geral": [
        ("dor_intensa", "Dor intensa", "Outra dor muito forte, insuportável (qualquer lugar do corpo)", "LARANJA"),
        ("febre", "Febre", "Febre ou sensação de febre", "VERDE"),
        ("dor_moderada", "Dor moderada", "Outra dor moderada (barriga, costas, garganta etc.)", "VERDE"),
        ("dor_leve", "Dor leve", "Outra dor leve", "VERDE"),
        ("calafrios", "Calafrios", "Calafrios, tremedeira de frio", "VERDE"),
        ("fraqueza", "Fraqueza/cansaço", "Fraqueza, cansaço, corpo mole", "VERDE"),
        ("sinais_desidratacao", "Desidratação", "Boca muito seca, urinando pouco, urina escura", "VERDE"),
        ("sede_excessiva", "Sede excessiva", "Muita sede e urinando muito", "VERDE"),
        ("outro_sintoma", "Outro sintoma", "Outro sintoma que não se encaixa em nenhuma outra chave", "VERDE"),
        ("perda_apetite", "Falta de apetite", "Falta de apetite", "AZUL"),
    ],
}

# Sintomas que a árvore entende (chave -> descrição). A LLM deve usar exatamente estas chaves.
SINTOMAS: dict[str, str] = {k: d for itens in CATALOGO.values() for k, _, d, _ in itens}
ROTULOS: dict[str, str] = {k: r for itens in CATALOGO.values() for k, r, _, _ in itens}
COR_BASE: dict[str, str | None] = {k: c for itens in CATALOGO.values() for k, _, _, c in itens}

ORDEM_CORES = ("VERMELHO", "LARANJA", "AMARELO", "VERDE", "AZUL")  # do mais grave para o mais leve


def _com_cor(cor: str | None) -> tuple[str, ...]:
    return tuple(k for k, c in COR_BASE.items() if c == cor)


ALARME = _com_cor("VERMELHO")
MUITO_URGENTES = _com_cor("LARANJA")
MODERADOS = _com_cor("AMARELO")
LEVES = _com_cor("VERDE")
MINIMOS = _com_cor("AZUL")
FATORES_RISCO = _com_cor(None)

# Sintomas que, com PA muito alta, indicam lesão de órgão-alvo (emergência hipertensiva)
ORGAO_ALVO = ("dor_toracica", "falta_de_ar", "cefaleia_intensa", "falta_de_ar_grave",
              "cefaleia_subita", "alteracao_visual_subita")
SANGRAMENTOS = ("sangramento_moderado", "sangramento_nasal", "sangramento_vaginal", "fezes_com_sangue",
                "vomito_com_sangue", "tosse_com_sangue", "sangue_na_urina")

# Faixas aceitas para os sinais vitais (rejeita erro de digitação / leitura inválida do sensor)
LIMITES = {
    "pas": (50, 300),    # mmHg
    "pad": (30, 200),    # mmHg
    "fc": (20, 250),     # bpm
    "spo2": (50, 100),   # %
    "temp": (30.0, 45.0) # °C
}

CLASSES = {
    "VERMELHO": {"prioridade": "Emergência", "tempo_alvo_min": 0,
                 "orientacao": "Atendimento imediato. Procure uma emergência agora ou ligue 192 (SAMU)."},
    "LARANJA": {"prioridade": "Muito urgente", "tempo_alvo_min": 10,
                "orientacao": "Precisa de atendimento médico em até 10 minutos."},
    "AMARELO": {"prioridade": "Urgente", "tempo_alvo_min": 60,
                "orientacao": "Precisa de atendimento médico em até 60 minutos."},
    "VERDE": {"prioridade": "Pouco urgente", "tempo_alvo_min": 120,
              "orientacao": "Pode aguardar atendimento (até 120 minutos)."},
    "AZUL": {"prioridade": "Não urgente", "tempo_alvo_min": 240,
             "orientacao": "Caso não urgente. Pode procurar atendimento na unidade básica de saúde."},
}


# Dados do paciente
SEXOS = {"F": "feminino", "M": "masculino"}
DEFICIENCIAS = {
    "fisica": "Deficiência física",
    "visual": "Deficiência visual",
    "auditiva": "Deficiência auditiva",
    "intelectual": "Deficiência intelectual ou mental",
}
SO_FEMININO = ("gestante", "perda_liquido_contracoes", "bebe_mexendo_menos", "sangramento_vaginal")
SO_MASCULINO = ("dor_testicular_subita",)
IDADE_IDOSO = 65               # fator de risco clínico
IDADE_PRIORIDADE_LEGAL = 60    # Estatuto da Pessoa Idosa / Lei 10.048/2000
IDADE_ADULTO = 16              # o NEWS2 foi validado em adultos
IDADE_MAXIMA = 130


class DadosInvalidos(ValueError):
    """Sinal vital fora da faixa aceita ou sintoma desconhecido."""


# --------------------------------------------------------------------------- #
# NEWS2 adaptado (FC, PAS, SpO2, temperatura)
# --------------------------------------------------------------------------- #

def pontos_news2(fc: float, pas: float, spo2: float, temp: float) -> dict[str, int]:
    """Pontos NEWS2 de cada parâmetro medido pelos sensores."""
    # Frequência cardíaca
    if fc <= 40 or fc >= 131: p_fc = 3
    elif fc >= 111: p_fc = 2
    elif fc <= 50 or fc >= 91: p_fc = 1
    else: p_fc = 0
    # Pressão arterial sistólica
    if pas <= 90 or pas >= 220: p_pas = 3
    elif pas <= 100: p_pas = 2
    elif pas <= 110: p_pas = 1
    else: p_pas = 0
    # Saturação de oxigênio (escala 1)
    if spo2 <= 91: p_spo2 = 3
    elif spo2 <= 93: p_spo2 = 2
    elif spo2 <= 95: p_spo2 = 1
    else: p_spo2 = 0
    # Temperatura
    if temp <= 35.0: p_temp = 3
    elif temp >= 39.1: p_temp = 2
    elif temp <= 36.0 or temp >= 38.1: p_temp = 1
    else: p_temp = 0
    return {"fc": p_fc, "pas": p_pas, "spo2": p_spo2, "temp": p_temp}


# --------------------------------------------------------------------------- #
# Combinações (sintoma + sintoma, sintoma + sinal vital, sintoma + fator de risco)
# --------------------------------------------------------------------------- #

def _algum(s: set[str], *chaves: str) -> bool:
    return any(k in s for k in chaves)


def _todos(s: set[str], *chaves: str) -> bool:
    return all(k in s for k in chaves)


# Cada regra: (motivo, condição(sintomas, vitais) -> bool)
Regra = tuple[str, Callable[[set[str], dict[str, float]], bool]]

COMBINACOES_ALARME: list[Regra] = [
    ("Suspeita de anafilaxia (alergia na pele com sintoma respiratório ou sensação de desmaio)",
     lambda s, v: "alergia_pele" in s and _algum(s, "falta_de_ar", "falta_de_ar_grave", "chiado_no_peito", "quase_desmaio")),
    ("Suspeita de meningite grave (rigidez de nuca com manchas roxas na pele)",
     lambda s, v: _todos(s, "rigidez_nuca", "manchas_roxas_pele")),
]

COMBINACOES_MUITO_URGENTES: list[Regra] = [
    ("Dor no peito com sinais associados (possível síndrome coronariana)",
     lambda s, v: "dor_toracica" in s and _algum(s, "sudorese_fria", "nausea", "vomito", "falta_de_ar",
                                                  "palpitacao", "quase_desmaio")),
    ("Cardiopata com sintoma cardíaco",
     lambda s, v: "cardiopata" in s and _algum(s, "dor_toracica", "falta_de_ar", "palpitacao", "quase_desmaio")),
    ("Frequência cardíaca muito alterada com sintomas",
     lambda s, v: (v["fc"] >= 131 or v["fc"] <= 40)
     and _algum(s, "dor_toracica", "falta_de_ar", "palpitacao", "quase_desmaio", "tontura")),
    ("Falta de ar com saturação baixa (SpO2 92-93%)",
     lambda s, v: v["spo2"] <= 93 and _algum(s, "falta_de_ar", "chiado_no_peito")),
    ("Doença respiratória crônica em crise com saturação reduzida",
     lambda s, v: "doenca_respiratoria_cronica" in s and v["spo2"] <= 94 and _algum(s, "falta_de_ar", "chiado_no_peito")),
    ("Suspeita de embolia pulmonar (inchaço em uma perna com sintoma respiratório)",
     lambda s, v: "inchaco_perna_unilateral" in s and _algum(s, "falta_de_ar", "dor_toracica", "tosse_com_sangue")),
    ("Suspeita de meningite (febre com rigidez de nuca)",
     lambda s, v: "rigidez_nuca" in s and ("febre" in s or v["temp"] >= 38.1)),
    ("Febre com manchas roxas na pele",
     lambda s, v: "manchas_roxas_pele" in s and ("febre" in s or v["temp"] >= 38.1)),
    ("Febre em pessoa com imunidade baixa",
     lambda s, v: "imunossuprimido" in s and ("febre" in s or v["temp"] >= 38.1)),
    ("Pancada na cabeça com sinal de gravidade",
     lambda s, v: "trauma_craniano" in s and _algum(s, "vomito", "vomito_persistente", "cefaleia_intensa",
                                                     "tontura", "anticoagulante")),
    ("Sangramento em uso de anticoagulante",
     lambda s, v: "anticoagulante" in s and _algum(s, *SANGRAMENTOS)),
    ("Sangramento com sinais de perda de sangue importante (pressão baixa ou coração acelerado)",
     lambda s, v: _algum(s, *SANGRAMENTOS) and (v["pas"] <= 100 or v["fc"] >= 111)),
    ("Gestante com sangramento ou dor abdominal",
     lambda s, v: "gestante" in s and _algum(s, "sangramento_vaginal", "dor_abdominal")),
    ("Suspeita de pré-eclâmpsia (gestante com pressão alta e sintomas)",
     lambda s, v: "gestante" in s and (v["pas"] >= 140 or v["pad"] >= 90)
     and _algum(s, "cefaleia", "cefaleia_intensa", "dor_abdominal", "nausea", "inchaco_pernas")),
    ("Suspeita de descompensação do diabetes (sede excessiva com vômito, dor abdominal ou falta de ar)",
     lambda s, v: _todos(s, "diabetico", "sede_excessiva")
     and _algum(s, "vomito", "vomito_persistente", "dor_abdominal", "falta_de_ar")),
]

COMBINACOES_MODERADAS: list[Regra] = [
    ("Vômito ou diarreia com sinais de desidratação",
     lambda s, v: _algum(s, "vomito", "diarreia")
     and (_algum(s, "sinais_desidratacao", "tontura") or v["pas"] <= 100 or v["fc"] >= 111)),
    ("Dor abdominal com febre",
     lambda s, v: "dor_abdominal" in s and ("febre" in s or v["temp"] >= 38.1)),
    ("Suspeita de infecção urinária complicada (sintoma urinário com febre)",
     lambda s, v: "dor_ao_urinar" in s and ("febre" in s or v["temp"] >= 38.1)),
    ("Suspeita de pneumonia (febre e tosse com saturação reduzida)",
     lambda s, v: "tosse" in s and ("febre" in s or v["temp"] >= 38.1) and v["spo2"] <= 95),
    ("Pressão alta com sintomas",
     lambda s, v: (v["pas"] >= 160 or v["pad"] >= 100)
     and _algum(s, "cefaleia", "tontura", "sangramento_nasal", "nausea")),
    ("Idoso com febre",
     lambda s, v: "idoso" in s and ("febre" in s or v["temp"] >= 38.1)),
    ("Idoso com dor abdominal",
     lambda s, v: _todos(s, "idoso", "dor_abdominal")),
    ("Diabético com sinais de hipoglicemia (tremores, tontura ou fraqueza)",
     lambda s, v: "diabetico" in s and _algum(s, "tremores", "tontura", "fraqueza")),
    ("Diabético com ferida infectada",
     lambda s, v: _todos(s, "diabetico", "ferida_infectada")),
    ("Mordida de animal em pessoa com imunidade baixa",
     lambda s, v: _todos(s, "imunossuprimido", "mordida_animal")),
]


# --------------------------------------------------------------------------- #
# Validação
# --------------------------------------------------------------------------- #

def validar(vitais: dict[str, Any], sintomas: list[str]) -> tuple[dict[str, float], set[str]]:
    v: dict[str, float] = {}
    for campo, (mn, mx) in LIMITES.items():
        if campo not in vitais or vitais[campo] is None:
            raise DadosInvalidos(f"Sinal vital ausente: '{campo}'.")
        try:
            valor = float(str(vitais[campo]).replace(",", "."))
        except ValueError:
            raise DadosInvalidos(f"Valor inválido para '{campo}': {vitais[campo]!r}.")
        if not (mn <= valor <= mx):
            raise DadosInvalidos(f"'{campo}' = {valor} fora da faixa aceita ({mn} a {mx}).")
        v[campo] = valor
    if v["pad"] >= v["pas"]:
        raise DadosInvalidos("A pressão diastólica (PAD) deve ser menor que a sistólica (PAS).")

    desconhecidos = [s for s in sintomas if s not in SINTOMAS]
    if desconhecidos:
        raise DadosInvalidos(f"Sintoma(s) desconhecido(s): {desconhecidos}. "
                             f"Use apenas: {list(SINTOMAS)}.")
    return v, set(sintomas)


def validar_perfil(idade: Any, sexo: Any, deficiencias: Any) -> tuple[int | None, str | None, list[str]]:
    if idade is not None:
        try:
            idade = int(idade)
        except (TypeError, ValueError):
            raise DadosInvalidos(f"Idade inválida: {idade!r}.")
        if not (0 <= idade <= IDADE_MAXIMA):
            raise DadosInvalidos(f"Idade {idade} fora da faixa aceita (0 a {IDADE_MAXIMA}).")
    if sexo is not None and sexo not in SEXOS:
        raise DadosInvalidos(f"Sexo inválido: {sexo!r}. Use {list(SEXOS)}.")
    deficiencias = list(dict.fromkeys(deficiencias or []))
    desconhecidas = [d for d in deficiencias if d not in DEFICIENCIAS]
    if desconhecidas:
        raise DadosInvalidos(f"Deficiência desconhecida: {desconhecidas}. Use {list(DEFICIENCIAS)}.")
    return idade, sexo, deficiencias


def aplicar_perfil(s: set[str], idade: int | None, sexo: str | None,
                   deficiencias: list[str]) -> tuple[list[str], list[str]]:
    """Ajusta os sintomas pelo perfil do paciente (altera `s`) e devolve
    (observações, motivos de atendimento prioritário)."""
    observacoes: list[str] = []

    incompativeis = SO_FEMININO if sexo == "M" else SO_MASCULINO if sexo == "F" else ()
    ignorados = [x for x in incompativeis if x in s]
    if ignorados:
        s.difference_update(ignorados)
        observacoes.append(f"Ignorado por ser do sexo {SEXOS[sexo]}: " + ", ".join(ROTULOS[x] for x in ignorados))

    if idade is not None and idade >= IDADE_IDOSO and "idoso" not in s:
        s.add("idoso")
    if idade is not None and idade < IDADE_ADULTO:
        observacoes.append(f"Paciente com {idade} anos: o NEWS2 foi criado para adultos, "
                           "então a classificação deve ser confirmada pela enfermagem.")

    prioridade = [DEFICIENCIAS[d] for d in deficiencias]
    if idade is not None and idade >= IDADE_PRIORIDADE_LEGAL:
        prioridade.append(f"Pessoa idosa ({idade} anos)")
    if "gestante" in s:
        prioridade.append("Gestante")
    return observacoes, prioridade


# --------------------------------------------------------------------------- #
# Árvore de decisão
# --------------------------------------------------------------------------- #

def classificar_risco(pas: float, pad: float, fc: float, spo2: float, temp: float,
                      sintomas: list[str] | None = None, idade: int | None = None,
                      sexo: str | None = None, deficiencias: list[str] | None = None) -> dict[str, Any]:
    """
    Classifica o risco do usuário.

    Parâmetros
    ----------
    pas, pad     : pressão arterial sistólica / diastólica (mmHg) — Omron HEM-7156T
    fc           : frequência cardíaca (bpm) — Omron ou relógio
    spo2         : saturação de oxigênio (%) — relógio
    temp         : temperatura corporal (°C) — sensor de temperatura
    sintomas     : lista de chaves de SINTOMAS (sintomas e fatores de risco) que o usuário
                   relatou (ex.: ["febre", "falta_de_ar", "diabetico"])
    idade        : idade em anos, da identificação (opcional)
    sexo         : "F" ou "M", da identificação (opcional)
    deficiencias : chaves de DEFICIENCIAS, da identificação (opcional)

    Retorno
    -------
    dict com: cor, prioridade, tempo_alvo_min, orientacao, nivel, motivo,
              outros_achados (demais regras que dispararam),
              atendimento_prioritario e motivos_prioridade (prioridade legal dentro da cor),
              observacoes (avisos sobre o perfil do paciente),
              news2 (total e pontos por parâmetro), dados usados.
    """
    v, s = validar({"pas": pas, "pad": pad, "fc": fc, "spo2": spo2, "temp": temp},
                   list(sintomas or []))
    idade, sexo, deficiencias = validar_perfil(idade, sexo, deficiencias)
    observacoes, motivos_prioridade = aplicar_perfil(s, idade, sexo, deficiencias)
    pts = pontos_news2(v["fc"], v["pas"], v["spo2"], v["temp"])
    total = sum(pts.values())

    # Todas as regras que disparam, na ordem da árvore. A primeira da cor mais grave decide.
    achados: list[dict[str, str]] = []

    def achado(cor: str, nivel: str, motivo: str) -> None:
        achados.append({"cor": cor, "nivel": nivel, "motivo": motivo})

    def relatados(grupo: tuple[str, ...]) -> list[str]:
        return [ROTULOS[x] for x in grupo if x in s]

    # N1 — sinais de alarme
    alarme = relatados(ALARME)
    if alarme:
        achado("VERMELHO", "N1", "Sinal de alarme relatado: " + ", ".join(alarme))
    for motivo, condicao in COMBINACOES_ALARME:
        if condicao(s, v):
            achado("VERMELHO", "N1", motivo)

    # N2 — sinal vital crítico
    if v["spo2"] <= 91:
        achado("VERMELHO", "N2", f"Saturação de oxigênio crítica (SpO2 = {v['spo2']:g}%)")
    if v["pas"] <= 90:
        achado("VERMELHO", "N2", f"Pressão arterial muito baixa (PAS = {v['pas']:g} mmHg)")
    if v["temp"] >= 41:
        achado("LARANJA", "N2", f"Temperatura muito alta ({v['temp']:g} °C)")

    # N3 — crise hipertensiva
    pa = f"PA = {v['pas']:g}/{v['pad']:g} mmHg"
    if v["pas"] >= 180 or v["pad"] >= 120:
        alvo = relatados(ORGAO_ALVO)
        if alvo:
            achado("VERMELHO", "N3", f"Emergência hipertensiva ({pa}) com " + ", ".join(x.lower() for x in alvo))
        else:
            achado("LARANJA", "N3", f"Urgência hipertensiva ({pa}) sem sintomas de órgão-alvo")
    if "gestante" in s and (v["pas"] >= 160 or v["pad"] >= 110):
        achado("VERMELHO", "N3", f"Pressão muito alta na gestação ({pa})")

    # N4 — escore NEWS2 adaptado
    mod = relatados(MODERADOS)
    isolado = [k for k, p in pts.items() if p == 3]
    if total >= 7:
        achado("LARANJA", "N4", f"Escore NEWS2 alto ({total} pontos)")
    elif total >= 5 or isolado:
        if mod:
            achado("LARANJA", "N4", f"Sinais vitais alterados (NEWS2 = {total}) com sintoma moderado: " + ", ".join(mod))
        if total >= 5:
            achado("AMARELO", "N4", f"Escore NEWS2 médio ({total} pontos)")
        else:
            nomes = {"fc": "frequência cardíaca", "pas": "pressão sistólica", "spo2": "saturação", "temp": "temperatura"}
            achado("AMARELO", "N4", "Parâmetro isolado muito alterado: "
                   + ", ".join(f"{nomes[k]} = {v[k]:g}" for k in isolado))

    # N5 — sintomas e combinações
    urg = relatados(MUITO_URGENTES)
    if urg:
        achado("LARANJA", "N5", "Sintoma muito urgente: " + ", ".join(urg))
    for motivo, condicao in COMBINACOES_MUITO_URGENTES:
        if condicao(s, v):
            achado("LARANJA", "N5", motivo)
    if mod:
        achado("AMARELO", "N5", "Sintoma moderado: " + ", ".join(mod))
    for motivo, condicao in COMBINACOES_MODERADAS:
        if condicao(s, v):
            achado("AMARELO", "N5", motivo)

    # N6 — leve / sem alteração
    leves = relatados(LEVES)
    minimos = relatados(MINIMOS)
    if total >= 1 or leves:
        partes = [f"NEWS2 = {total}"] if total >= 1 else []
        achado("VERDE", "N6", "Alteração leve: " + "; ".join(partes + leves))
    if minimos:
        achado("AZUL", "N6", "Queixa leve, sem sinais de urgência: " + ", ".join(minimos))
    achado("AZUL", "N6", "Sinais vitais normais e sem sintomas relevantes")

    principal = min(achados, key=lambda a: ORDEM_CORES.index(a["cor"]))  # empate: o primeiro da árvore
    outros = [a for a in achados[:-1] if a is not principal]
    return {
        "cor": principal["cor"],
        **CLASSES[principal["cor"]],
        "nivel": principal["nivel"],
        "motivo": principal["motivo"],
        "outros_achados": outros,
        "atendimento_prioritario": bool(motivos_prioridade),
        "motivos_prioridade": motivos_prioridade,
        "observacoes": observacoes,
        "news2": {"total": total, "pontos": pts},
        "dados": {"vitais": v, "sintomas": sorted(s),
                  "perfil": {"idade": idade, "sexo": sexo, "deficiencias": deficiencias}},
    }


# --------------------------------------------------------------------------- #
# Integração com a LLM
# --------------------------------------------------------------------------- #

# Schema da ferramenta no formato JSON Schema (aceito pelas APIs de LLM com function calling).
TOOL_SCHEMA = {
    "name": "classificar_risco",
    "description": (
        "Classifica o risco do usuário (cores do Protocolo de Manchester) a partir dos sinais "
        "vitais medidos pelos sensores e dos sintomas relatados. Sempre use esta ferramenta para "
        "decidir a classificação; nunca classifique por conta própria."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pas": {"type": "number", "description": "Pressão arterial sistólica (mmHg)"},
            "pad": {"type": "number", "description": "Pressão arterial diastólica (mmHg)"},
            "fc": {"type": "number", "description": "Frequência cardíaca (bpm)"},
            "spo2": {"type": "number", "description": "Saturação de oxigênio (%)"},
            "temp": {"type": "number", "description": "Temperatura corporal (°C)"},
            "sintomas": {
                "type": "array",
                "items": {"type": "string", "enum": list(SINTOMAS)},
                "description": "Sintomas e fatores de risco relatados pelo usuário. Significados: "
                               + "; ".join(f"{k} = {d}" for k, d in SINTOMAS.items()),
            },
            "idade": {"type": "integer", "description": "Idade em anos (da identificação)"},
            "sexo": {"type": "string", "enum": list(SEXOS), "description": "F = feminino, M = masculino"},
            "deficiencias": {
                "type": "array",
                "items": {"type": "string", "enum": list(DEFICIENCIAS)},
                "description": "Deficiências informadas na identificação",
            },
        },
        "required": ["pas", "pad", "fc", "spo2", "temp", "sintomas"],
    },
}


def executar_ferramenta(argumentos: dict[str, Any] | str) -> str:
    """Ponto de entrada para a LLM: recebe os argumentos (dict ou JSON) e devolve JSON."""
    if isinstance(argumentos, str):
        argumentos = json.loads(argumentos)
    try:
        r = classificar_risco(**argumentos)
    except (DadosInvalidos, TypeError) as e:
        r = {"erro": str(e)}
    return json.dumps(r, ensure_ascii=False)
