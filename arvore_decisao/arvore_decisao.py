"""
Árvore de decisão para classificação de risco — TCC 2026 (Triagem de Sintomas).

Este módulo é o "motor" da classificação. Ele é independente da LLM:
  - chamado pelo teste manual (teste_manual.py);
  - chamado pelo backend da triagem (pasta backend/), que recebe da LLM
    a lista de sintomas e dos sensores os sinais vitais.

A LLM NÃO decide a cor. Ela só transforma o que o usuário disse em chaves de sintomas
e repassa os sinais vitais vindos dos sensores. Quem decide é a árvore.

PROTOCOLO DE REFERÊNCIA
  Todas as regras seguem um único documento, citado em cada regra:
    Protocolo de Classificação de Risco (Baseado no protocolo de MANCHESTER).
    Secretaria Municipal de Saúde de Aparecida de Goiânia, 2025.
  - Cores e tempos (seção 5); discriminadores gerais e escala de dor (seção 6);
    fluxograma geral (seção 8); 24 fluxogramas de adultos (seção 9);
    temperatura (Anexo II, igual ao UNA-SUS/UFSC); sinais vitais em adultos (Anexo III).
  - Quando o protocolo dá duas cores para a mesma faixa (ex.: "Amarelo/Laranja"),
    vale a mais grave (lado seguro).
  - Sintoma sem discriminador próprio segue o fluxograma em que melhor se encaixa:
    "Evento recente (< 7 dias)" = verde quando o fluxograma tem esse item; senão, azul.
  - Única exceção, marcada [exceção obstétrica]: queixas da gestação. O protocolo manda a
    gestante para avaliação própria (seção 4.2); até adotar o protocolo obstétrico do
    Ministério da Saúde, as regras da gestação continuam como estavam.
  - Pulso irregular avisado pelo Omron: definição de "pulso anormal" do Manchester
    (Rev. Gaúcha Enferm., discriminadores do STM), que o protocolo não detalha.

Entradas
  - 5 sinais vitais (PAS, PAD, FC, SpO2, temperatura) e o aviso de batimento irregular
    do medidor de pressão (Omron);
  - sintomas relatados (chaves do CATALOGO, organizadas por sistema do corpo), cada um com a
    cor do discriminador correspondente no protocolo; a intensidade da dor entra pelas chaves
    dor_leve (1-3), dor_moderada (4-6) e dor_intensa (7-10), como na escala da seção 6;
  - a duração: `queixa_antiga` = começou há mais de 7 dias e não piorou.

Ordem de avaliação (vale a cor mais grave encontrada; no empate, a regra que vem antes):
  N1  Risco de morte (vermelho): via aérea, respiração, cianose, convulsão ativa, não responde,
      hemorragia incontrolável, choque (PAS <= 80 com FC >= 140 ou <= 40, suor frio ou
      alteração da consciência) e choque anafilático
  N2  Sinais vitais medidos (Anexos II e III):
        FC < 40 vermelho; 40-59 laranja; 101-149 amarelo; >= 150 laranja; ritmo irregular laranja
        SpO2 < 90% vermelho; 90-94% amarelo
        PAS < 80 ou PAD < 50 laranja; PAS >= 200 laranja; PAS 160-199 ou PAD >= 100 amarelo
        Temperatura >= 41 laranja; 38,5-40,9 amarelo; 37,5-38,4 verde; <= 34 vermelho; 34,1-36 verde
  N3  Gestação [exceção obstétrica]
  N4  Discriminadores dos fluxogramas: cor de cada sintoma e combinações do protocolo
      (dor precordial, falta de ar com SpO2 < 92%, disúria ou dor de garganta com febre,
      sangramento vaginal na gestação)
  N5  Duração: problema há mais de 7 dias que daria verde passa para azul
  N6  Nenhum discriminador: azul

Todas as regras que dispararam (não só a que definiu a cor) voltam em `outros_achados`.
O escore NEWS2 continua sendo calculado e devolvido só como informação: não decide a cor.

Dados do paciente (vêm da identificação no totem, não da conversa)
  - idade: com 65 anos ou mais, a chave "idoso" é registrada (não muda a cor); abaixo de
    14 anos o protocolo usa os fluxogramas pediátricos, então o resultado pede que a
    enfermagem confirme.
  - sexo: no masculino, chaves só possíveis no feminino (gestante, sangramento vaginal...)
    são ignoradas; no feminino, a dor testicular é ignorada.
  - fatores de risco (diabetes, coração, asma, imunidade baixa, anticoagulante) são
    registrados, mas, como no protocolo, não mudam a cor.
  - deficiências, 60 anos ou mais e gestação dão direito a atendimento prioritário dentro
    da cor (Lei 10.048/2000), sem mudar a cor.
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
    # cor-base None = não classifica sozinho (fatores de risco e a duração da queixa).
    # Entre colchetes no comentário: o fluxograma/seção do protocolo de onde vem a cor.
    "Fatores de risco": [
        ("gestante", "Gestante", "Está grávida ou pode estar grávida", None),
        ("idoso", "Idoso (65+)", "Tem 65 anos ou mais", None),
        ("diabetico", "Diabético", "Tem diabetes", None),
        ("cardiopata", "Doença do coração", "Tem doença do coração (infarto prévio, insuficiência cardíaca, arritmia, stent)", None),
        ("doenca_respiratoria_cronica", "Asma/DPOC", "Tem asma, bronquite crônica, enfisema ou DPOC", None),
        ("imunossuprimido", "Imunidade baixa", "Faz quimioterapia, é transplantado, vive com HIV ou usa corticoide em dose alta", None),
        ("anticoagulante", "Usa anticoagulante", "Usa remédio para afinar o sangue (varfarina, rivaroxabana, apixabana etc.)", None),
    ],
    "Duração da queixa": [
        # Fluxograma geral: "Problema recente?" não -> azul; "Evento > 7 dias" -> azul nos fluxogramas
        ("queixa_antiga", "Há mais de 7 dias", "Os sintomas começaram há mais de 7 dias e não pioraram nos últimos dias", None),
    ],
    "Neurológico": [
        ("inconsciente", "Não responde", "Desacordado ou não responde quando chamado", "VERMELHO"),  # Paciente não responsivo [fluxograma geral]
        ("convulsao", "Convulsionando", "Está tendo convulsão agora", "VERMELHO"),  # Convulsão ativa [Convulsão]
        ("confusao_mental", "Confusão mental", "Confusão, desorientação ou sonolência que começaram de repente", "LARANJA"),  # Alteração súbita da consciência [Mal-estar, Dor de cabeça]
        ("deficit_neurologico", "Déficit neurológico", "Fraqueza/dormência em um lado do corpo, fala enrolada ou boca torta, nas últimas 24 horas", "LARANJA"),  # Déficit neurológico agudo [Desmaio, Dor de cabeça]
        ("cefaleia_subita", "Dor de cabeça súbita", "Dor de cabeça que começou de repente, a pior da vida", "LARANJA"),  # Dor intensa (7-10) [Dor de cabeça]
        ("cefaleia_intensa", "Dor de cabeça forte", "Dor de cabeça muito forte (nota 7 a 10)", "LARANJA"),  # Dor intensa (7-10) [Dor de cabeça]
        ("alteracao_visual_subita", "Perda súbita da visão", "Perdeu a visão de repente", "LARANJA"),  # Perda aguda completa da visão [Dor de cabeça; Queixas oculares]
        ("rigidez_nuca", "Rigidez de nuca", "Pescoço duro, dor ao encostar o queixo no peito", "LARANJA"),  # Sinais de meningismo [SNC, seção 10]
        ("desmaio_recente", "Desmaiou", "Desmaiou ou perdeu a consciência e já voltou", "AMARELO"),  # História de inconsciência [Desmaio; Dor de cabeça]
        ("convulsao_recente", "Convulsão recente", "Teve convulsão nas últimas 12 horas e agora está acordado", "AMARELO"),  # Crise convulsiva há menos de 12h e alerta [Convulsão]
        ("quase_desmaio", "Sensação de desmaio", "Sensação de que vai desmaiar, visão escurecendo", "VERDE"),  # Evento de início < 6 horas [Desmaio, vertigem]
        ("cefaleia", "Dor de cabeça", "Dor de cabeça", "VERDE"),  # Dor leve (1-3) / Evento recente [Dor de cabeça]
        ("tontura", "Tontura", "Tontura ou vertigem (tudo girando)", "VERDE"),  # Vertigem [Otorrinolaringológicas]
        ("formigamento", "Formigamento", "Formigamento ou dormência em mãos, pés ou rosto (dos dois lados)", "VERDE"),  # Evento recente [Vasculares]
        ("tremores", "Tremores", "Tremores no corpo ou nas mãos", "AZUL"),  # sem discriminador [Mal-estar]
    ],
    "Coração e circulação": [
        ("dor_toracica_intensa", "Dor no peito intensa", "Dor no peito forte, em aperto ou peso, que pode ir para o braço, pescoço ou mandíbula", "LARANJA"),  # Dor precordial / Dor intensa [Dor torácica]
        ("dor_toracica", "Dor no peito", "Dor ou desconforto no peito (leve ou moderado)", "AMARELO"),  # Dor moderada (4-6) [Dor torácica]
        ("palpitacao", "Palpitação", "Coração acelerado, disparado ou batendo fora do ritmo", "VERDE"),  # Evento recente [Dor torácica]; o pulso medido decide o resto
        ("sudorese_fria", "Suor frio", "Suor frio, pele pálida e pegajosa", "VERDE"),  # Evento recente [Dor torácica]; entra no choque e na dor precordial
        ("inchaco_perna_unilateral", "Inchaço em uma perna", "Uma perna só inchada, dolorida, quente ou vermelha", "VERDE"),  # Sinais flogísticos / Evento recente [Vasculares]
        ("inchaco_pernas", "Inchaço nas pernas", "Inchaço nas duas pernas ou nos pés", "VERDE"),  # Evento recente [Vasculares]
    ],
    "Respiratório": [
        ("engasgo", "Engasgo/sufocamento", "Engasgado, sufocando, não consegue respirar ou falar", "VERMELHO"),  # Obstrução de vias aéreas [Respiratórias]
        ("labios_roxos", "Lábios roxos", "Lábios, rosto ou pontas dos dedos roxos/azulados", "VERMELHO"),  # Cianose central [Vasculares]
        ("falta_de_ar_grave", "Falta de ar grave", "Falta de ar em repouso, não consegue completar uma frase", "LARANJA"),  # Respiração inadequada / Fadiga respiratória [Respiratórias]
        ("falta_de_ar", "Falta de ar", "Falta de ar", "AMARELO"),  # Dispneia com saturação > 92% [Respiratórias]
        ("tosse_com_sangue", "Tosse com sangue", "Tosse com sangue", "AMARELO"),  # História de hemoptise [Mal-estar] (verde em Respiratórias: vale a mais grave)
        ("chiado_no_peito", "Chiado no peito", "Chiado no peito, crise de asma", "VERDE"),  # Chiado [Respiratórias]
        ("tosse", "Tosse", "Tosse seca ou com catarro", "VERDE"),  # Tosse [Respiratórias]
        ("dor_garganta", "Dor de garganta", "Dor de garganta, rouquidão", "VERDE"),  # Dor de garganta [Respiratórias; Dor de garganta]
        ("coriza", "Coriza/nariz entupido", "Coriza, nariz entupido, espirros", "VERDE"),  # Rinorreia/coriza [Respiratórias]
    ],
    "Digestivo": [
        ("dor_abdominal_intensa", "Dor de barriga intensa", "Dor na barriga muito forte (nota 7 a 10), barriga dura", "LARANJA"),  # Dor intensa (7-10) [Dor abdominal]
        ("vomito_com_sangue", "Vômito com sangue", "Vômito com sangue ou parecendo borra de café", "LARANJA"),  # Hematêmese [Dor abdominal; Sangramentos]
        ("vomito_persistente", "Vômitos persistentes", "Vomitou 3 vezes ou mais em 24 horas, não segura líquidos", "AMARELO"),  # Vômitos persistentes [Dor abdominal]
        ("fezes_com_sangue", "Sangue nas fezes", "Fezes com sangue ou pretas como piche", "AMARELO"),  # Relato de fezes pretas ou em groselha [Dor abdominal; Sangramentos]
        ("dor_abdominal", "Dor de barriga", "Dor na barriga ou no estômago, cólica", "VERDE"),  # Dor leve (1-3) [Dor abdominal]
        ("ictericia", "Pele/olhos amarelos", "Pele ou olhos amarelados", "VERDE"),  # Evento recente [Dor abdominal]
        ("nausea", "Enjoo", "Enjoo, náusea", "VERDE"),  # Evento de início < 6 horas [Diarreia e vômitos]
        ("vomito", "Vômito", "Vomitou poucas vezes", "VERDE"),  # Vômitos [Dor abdominal]
        ("diarreia", "Diarreia", "Diarreia", "VERDE"),  # Evento recente [Diarreia e vômitos]
        ("azia", "Azia", "Azia, queimação no estômago, refluxo", "VERDE"),  # Evento recente [Dor abdominal]
        ("dificuldade_engolir", "Dificuldade para engolir", "Dificuldade ou dor para engolir", "VERDE"),  # Dificuldade para deglutir [Dor de garganta]
        ("constipacao", "Prisão de ventre", "Prisão de ventre, gases", "VERDE"),  # Evento recente [Dor abdominal]
    ],
    "Urinário e reprodutivo": [
        ("dor_testicular_subita", "Dor testicular súbita", "Dor forte e súbita no testículo", "LARANJA"),  # Dor intensa (7-10) [Queixas urinárias]
        ("perda_liquido_contracoes", "Contrações/perda de líquido", "Gestante com contrações fortes ou perda de líquido", "LARANJA"),  # [exceção obstétrica]
        ("bebe_mexendo_menos", "Bebê mexendo menos", "Gestante que sente o bebê mexer bem menos ou parar de mexer", "LARANJA"),  # [exceção obstétrica]
        ("sangramento_vaginal", "Sangramento vaginal", "Sangramento vaginal fora da menstruação ou muito maior que o normal", "AMARELO"),  # Sangramento vaginal controlável [Sangramentos]
        ("retencao_urinaria", "Não consegue urinar", "Vontade de urinar mas não consegue, bexiga cheia e dolorida", "AMARELO"),  # Retenção urinária [Queixas urinárias]
        ("sangue_na_urina", "Sangue na urina", "Urina com sangue", "AMARELO"),  # Hematúria [Queixas urinárias]
        ("dor_ao_urinar", "Dor ao urinar", "Dor ou ardência ao urinar, urinando toda hora", "VERDE"),  # Disúria [Queixas urinárias]
        ("colica_menstrual", "Cólica/dor pélvica", "Cólica menstrual ou dor na parte baixa da barriga", "VERDE"),  # Dor leve (1-3) [Queixas urinárias]
        ("corrimento_genital", "Corrimento", "Corrimento, coceira ou ferida na região genital", "VERDE"),  # Presença de secreção [Queixas urinárias]
    ],
    "Alergia e pele": [
        ("inchaco_garganta", "Inchaço de língua/garganta", "Língua, lábios ou garganta inchando, dificuldade para respirar ou engolir", "VERMELHO"),  # Obstrução de vias aéreas (edema de língua) [Intoxicações; Mordeduras]
        ("alergia_pele", "Alergia na pele", "Urticária, placas vermelhas ou coceira pelo corpo", "VERDE"),  # Placas eritematosas de início súbito [Alterações cutâneas]
        ("erupcao_pele", "Manchas/bolhas na pele", "Manchas, bolhas ou feridas na pele", "VERDE"),  # Erupções secretantes ou bolhosas [Alterações cutâneas]
        ("manchas_roxas_pele", "Manchas roxas na pele", "Pintas ou manchas roxas/vermelhas que não somem ao apertar", "VERDE"),  # Púrpura [Mal-estar]
        ("ferida_infectada", "Ferida infectada", "Ferida ou furúnculo vermelho, quente, com pus", "VERDE"),  # Ferida infectada [Alterações cutâneas]
    ],
    "Trauma e acidentes": [
        ("sangramento_intenso", "Sangramento intenso", "Sangramento forte que não para mesmo apertando", "VERMELHO"),  # Hemorragia incontrolável [Politraumas]
        ("queimadura_grave", "Queimadura grave", "Queimadura grande, no rosto ou na cabeça", "VERMELHO"),  # Queimaduras extensas / na cabeça e face [Queimaduras]
        ("quimico_no_olho", "Produto químico no olho", "Produto químico caiu no olho", "VERMELHO"),  # Lesão ocular química aguda [Queixas oculares]
        ("trauma_grave", "Acidente grave", "Acidente de trânsito, queda de altura ou pancada muito forte", "LARANJA"),  # Mecanismo de trauma significativo [Politraumas]
        ("fratura_exposta", "Fratura exposta", "Osso aparecendo ou membro muito deformado", "LARANJA"),  # Deformidade local / Politrauma [Politraumas]
        ("intoxicacao", "Intoxicação", "Tomou remédio em excesso, veneno, produto de limpeza ou droga", "LARANJA"),  # História de overdose ou envenenamento [Alterações de comportamento]
        ("picada_animal_peconhento", "Picada de animal peçonhento", "Picada de cobra, escorpião ou aranha", "LARANJA"),  # Acidente com animal peçonhento [Alterações cutâneas]
        ("trauma_craniano", "Pancada na cabeça", "Bateu a cabeça nos últimos dias", "AMARELO"),  # História de trauma craniano recente [Desmaio; Convulsão]
        ("sangramento_moderado", "Sangramento", "Sangramento que diminui ao apertar, mas não para de vez", "AMARELO"),  # Hemorragia controlável [Politraumas]
        ("ferida_profunda", "Corte profundo", "Corte profundo, que precisa de pontos", "AMARELO"),  # Ferida corto-contusa com necessidade de sutura [Alterações cutâneas]
        ("suspeita_fratura", "Suspeita de fratura", "Não consegue mexer ou apoiar o membro depois de queda/pancada", "VERDE"),  # Suspeita de fratura com dor leve [Politraumas]
        ("corte_leve", "Corte/arranhão", "Corte pequeno ou arranhão", "VERDE"),  # Ferida superficial [Alterações cutâneas]
        ("entorse_contusao", "Torção/pancada", "Torção, pancada ou inchaço em braço, perna, pé ou mão", "VERDE"),  # Contusões e escoriações [Politraumas]
        ("queimadura_leve", "Queimadura leve", "Queimadura pequena", "VERDE"),  # Evento recente [Queimaduras]
        ("mordida_animal", "Mordida de animal", "Mordida ou arranhão de cachorro, gato ou outro animal", "VERDE"),  # Mordedura - acidente leve [Alterações cutâneas]
    ],
    "Olhos, ouvidos, nariz e boca": [
        ("sangramento_nasal", "Sangramento no nariz", "Sangramento pelo nariz", "VERDE"),  # Relato de epistaxe [Sangramentos]
        ("dor_olho", "Problema no olho", "Olho vermelho, dolorido, com secreção ou cisco", "VERDE"),  # Olho vermelho [Queixas oculares]
        ("dor_ouvido", "Dor de ouvido", "Dor de ouvido, secreção ou zumbido", "VERDE"),  # Dor/secreção [Otorrinolaringológicas]
        ("dor_dente", "Dor de dente", "Dor de dente ou na gengiva", "VERDE"),  # Dor leve [Alterações odontológicas]
    ],
    "Músculos e articulações": [
        ("dor_costas", "Dor nas costas", "Dor nas costas ou na lombar", "VERDE"),  # Dor leve / Evento recente [Dor na coluna]
        ("dor_articular", "Dor nas juntas", "Dor em articulações (joelho, ombro, punho etc.)", "VERDE"),  # Edema articular / Evento recente [Vasculares]
        ("dor_muscular", "Dor no corpo", "Dor muscular, dor no corpo todo", "VERDE"),  # Dor leve recente [Mal-estar]
    ],
    "Saúde mental": [
        ("agitacao_agressividade", "Agitação intensa", "Muito agitado, agressivo ou fora de controle", "LARANJA"),  # Extrema agitação [Alterações de comportamento]
        ("pensamento_suicida", "Pensamento suicida", "Pensa em se machucar ou tirar a própria vida", "AMARELO"),  # Potencial suicida [Alterações de comportamento]
        ("crise_ansiedade", "Crise de ansiedade", "Crise de ansiedade ou pânico, sensação de que vai morrer", "AMARELO"),  # Ataque de pânico [Alterações de comportamento]
        ("alucinacao", "Alucinação", "Vê ou ouve coisas que não existem", "AMARELO"),  # Alucinações ou desorientação [Alterações de comportamento]
        ("tristeza_desanimo", "Tristeza/ansiedade", "Tristeza, desânimo, ansiedade ou estresse sem crise", "AZUL"),  # Sintomas ansiosos/depressivos [Alterações de comportamento]
        ("insonia", "Insônia", "Dificuldade para dormir", "AZUL"),  # Sintomas depressivos [Alterações de comportamento]
    ],
    "Geral": [
        # Escala de dor (seção 6): leve 1-3, moderada 4-6, severa 7-10. Registrar junto com o local da dor.
        ("dor_intensa", "Dor intensa", "Dor muito forte, nota 7 a 10 (qualquer lugar do corpo)", "LARANJA"),  # Dor severa [fluxograma geral]
        ("dor_moderada", "Dor moderada", "Dor moderada, nota 4 a 6 (qualquer lugar do corpo)", "AMARELO"),  # Dor moderada [fluxograma geral]
        ("dor_leve", "Dor leve", "Dor leve, nota 1 a 3 (qualquer lugar do corpo)", "VERDE"),  # Dor leve [fluxograma geral]
        ("sinais_desidratacao", "Desidratação", "Muita sede com boca seca, urinando pouco, urina escura", "AMARELO"),  # Sinais de desidratação [Diarreia e vômitos]
        ("febre", "Febre", "Febre ou sensação de febre", "VERDE"),  # Febril [Mal-estar]
        ("calafrios", "Calafrios", "Calafrios, tremedeira de frio", "VERDE"),  # Febril [Mal-estar]
        ("outro_sintoma", "Outro sintoma", "Outro sintoma que não se encaixa em nenhuma outra chave", "VERDE"),  # Evento recente (lado seguro)
        ("fraqueza", "Fraqueza/cansaço", "Fraqueza, cansaço, corpo mole", "AZUL"),  # sem discriminador [Mal-estar]
        ("sede_excessiva", "Sede excessiva", "Muita sede e urinando muito", "AZUL"),  # sem discriminador [Mal-estar]
        ("perda_apetite", "Falta de apetite", "Falta de apetite", "AZUL"),  # Sintomas depressivos [Alterações de comportamento]
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
IDADE_ADULTO = 14              # abaixo disso o protocolo usa os fluxogramas pediátricos (seção 10)
IDADE_MAXIMA = 130

# Sinais vitais em adultos (Anexo III; temperatura pelo Anexo II). Faixa com duas cores: a mais grave.
FC_BRADI_GRAVE = 40      # FC < 40 -> vermelho
FC_BRADI = 60            # 40 a 59 -> laranja ("Amarelo/Laranja")
FC_TAQUI = 100           # 101 a 149 -> amarelo ("Verde/Amarelo")
FC_TAQUI_GRAVE = 150     # >= 150 -> laranja
SPO2_MUITO_BAIXA = 90    # < 90% -> vermelho ("Laranja/Vermelho")
SPO2_BAIXA = 95          # 90 a 94% -> amarelo ("Verde/Amarelo")
SPO2_DISPNEIA = 92       # falta de ar com saturação < 92% -> laranja [Queixas respiratórias]
PAS_HIPOTENSAO = 80      # PAS < 80 ou PAD < 50 -> laranja
PAD_HIPOTENSAO = 50
PAS_CRISE = 200          # PAS >= 200 -> laranja ("Amarelo/Laranja")
PAS_HIPERTENSAO = 160    # PAS 160-199 ou PAD >= 100 -> amarelo (estágios 2 e 3)
PAD_HIPERTENSAO = 100
PAS_CHOQUE = 80          # choque: PAS <= 80 com FC >= 140 ou <= 40 [Intoxicações; Mal-estar]
FC_CHOQUE_ALTA = 140
FC_CHOQUE_BAIXA = 40
TEMP_MUITO_QUENTE = 41.0 # >= 41 °C -> laranja (Anexo II)
TEMP_QUENTE = 38.5       # 38,5 a 40,9 °C -> amarelo
TEMP_FEBRICULA = 37.5    # 37,5 a 38,4 °C -> verde
TEMP_FEBRE = 37.8        # "Febre/Hipertermia" (Anexo III): usada nas combinações com febre
TEMP_HIPOTERMIA_GRAVE = 34.0  # <= 34 °C -> vermelho (hipotermia moderada)
TEMP_HIPOTERMIA = 36.0   # 34,1 a 36 °C -> verde ("Azul/Verde")


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


# Cada regra: (motivo, condição(sintomas, vitais) -> bool). Só combinações escritas no protocolo.
Regra = tuple[str, Callable[[set[str], dict[str, float]], bool]]


def _febre(s: set[str], v: dict[str, float]) -> bool:
    return "febre" in s or v["temp"] >= TEMP_FEBRE


COMBINACOES_ALARME: list[Regra] = [
    ("Sinais de choque: pressão baixa com pulso muito alterado, suor frio ou alteração da consciência "
     "[fluxogramas Intoxicações e Mal-estar]",
     lambda s, v: v["pas"] <= PAS_CHOQUE and (v["fc"] >= FC_CHOQUE_ALTA or v["fc"] <= FC_CHOQUE_BAIXA
                                              or _algum(s, "sudorese_fria", "confusao_mental", "inconsciente"))),
    ("Suspeita de choque anafilático (alergia com falta de ar, chiado, garganta inchando ou sensação de desmaio) "
     "[fluxograma Alterações odontológicas]",
     lambda s, v: "alergia_pele" in s and _algum(s, "falta_de_ar", "falta_de_ar_grave", "chiado_no_peito",
                                                 "inchaco_garganta", "quase_desmaio")),
]

COMBINACOES_MUITO_URGENTES: list[Regra] = [
    ("Dor precordial: dor no peito com suor frio, enjoo ou vômito [fluxograma Dor torácica]",
     lambda s, v: _algum(s, "dor_toracica", "dor_toracica_intensa") and _algum(s, "sudorese_fria", "nausea", "vomito")),
    ("Falta de ar com saturação abaixo de 92% [fluxograma Queixas respiratórias]",
     lambda s, v: v["spo2"] < SPO2_DISPNEIA and _algum(s, "falta_de_ar", "falta_de_ar_grave", "chiado_no_peito")),
    ("Sangramento vaginal na gestação [fluxograma Sangramentos]",
     lambda s, v: _todos(s, "gestante", "sangramento_vaginal")),
]

COMBINACOES_MODERADAS: list[Regra] = [
    ("Ardência ao urinar com febre [fluxograma Queixas urinárias]",
     lambda s, v: "dor_ao_urinar" in s and _febre(s, v)),
    ("Dor de garganta com febre [fluxograma Dor de garganta]",
     lambda s, v: "dor_garganta" in s and _febre(s, v)),
]

# [exceção obstétrica] O protocolo encaminha a gestante para avaliação própria (seção 4.2).
COMBINACOES_GESTACAO: list[tuple[str, str, Callable[[set[str], dict[str, float]], bool]]] = [
    ("VERMELHO", "Pressão muito alta na gestação",
     lambda s, v: v["pas"] >= 160 or v["pad"] >= 110),
    ("LARANJA", "Suspeita de pré-eclâmpsia (pressão alta com dor de cabeça, dor de barriga, enjoo ou inchaço)",
     lambda s, v: (v["pas"] >= 140 or v["pad"] >= 90)
     and _algum(s, "cefaleia", "cefaleia_intensa", "dor_abdominal", "nausea", "inchaco_pernas")),
    ("LARANJA", "Gestante com dor de barriga",
     lambda s, v: _algum(s, "dor_abdominal", "dor_abdominal_intensa")),
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
        observacoes.append(f"Paciente com {idade} anos: o protocolo usa fluxogramas e sinais vitais "
                           "pediátricos, então a classificação deve ser confirmada pela enfermagem.")

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
                      sexo: str | None = None, deficiencias: list[str] | None = None,
                      pulso_irregular: bool = False) -> dict[str, Any]:
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
    pulso_irregular : o medidor de pressão avisou batimento irregular (opcional)

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
    if not isinstance(pulso_irregular, bool):
        raise DadosInvalidos(f"pulso_irregular deve ser verdadeiro ou falso: {pulso_irregular!r}.")
    idade, sexo, deficiencias = validar_perfil(idade, sexo, deficiencias)
    observacoes, motivos_prioridade = aplicar_perfil(s, idade, sexo, deficiencias)
    pts = pontos_news2(v["fc"], v["pas"], v["spo2"], v["temp"])  # só informativo: não decide a cor
    total = sum(pts.values())

    # Todas as regras que disparam, na ordem da árvore. A cor mais grave decide.
    achados: list[dict[str, str]] = []

    def achado(cor: str, nivel: str, motivo: str) -> None:
        achados.append({"cor": cor, "nivel": nivel, "motivo": motivo})

    def relatados(grupo: tuple[str, ...]) -> list[str]:
        return [ROTULOS[x] for x in grupo if x in s]

    # N1 — risco de morte
    alarme = relatados(ALARME)
    if alarme:
        achado("VERMELHO", "N1", "Risco de morte: " + ", ".join(alarme))
    for motivo, condicao in COMBINACOES_ALARME:
        if condicao(s, v):
            achado("VERMELHO", "N1", motivo)

    # N2 — sinais vitais medidos (Anexo III; temperatura pelo Anexo II)
    fc, pa = v["fc"], f"{v['pas']:g}/{v['pad']:g} mmHg"
    if fc < FC_BRADI_GRAVE:
        achado("VERMELHO", "N2", f"Bradicardia grave (FC = {fc:g} bpm)")
    elif fc < FC_BRADI:
        achado("LARANJA", "N2", f"Bradicardia (FC = {fc:g} bpm)")
    elif fc >= FC_TAQUI_GRAVE:
        achado("LARANJA", "N2", f"Taquicardia acima de 150 (FC = {fc:g} bpm)")
    elif fc > FC_TAQUI:
        achado("AMARELO", "N2", f"Taquicardia (FC = {fc:g} bpm)")
    if pulso_irregular:
        achado("LARANJA", "N2", "Pulso anormal: ritmo irregular avisado pelo medidor de pressão")
    if v["spo2"] < SPO2_MUITO_BAIXA:
        achado("VERMELHO", "N2", f"Saturação muito baixa (SpO2 = {v['spo2']:g}%)")
    elif v["spo2"] < SPO2_BAIXA:
        achado("AMARELO", "N2", f"Saturação baixa (SpO2 = {v['spo2']:g}%)")
    if v["pas"] < PAS_HIPOTENSAO or v["pad"] < PAD_HIPOTENSAO:
        achado("LARANJA", "N2", f"Hipotensão (PA = {pa})")
    elif v["pas"] >= PAS_CRISE:
        achado("LARANJA", "N2", f"Crise hipertensiva (PA = {pa})")
    elif v["pas"] >= PAS_HIPERTENSAO or v["pad"] >= PAD_HIPERTENSAO:
        achado("AMARELO", "N2", f"Hipertensão moderada ou grave (PA = {pa})")
    t = v["temp"]
    if t >= TEMP_MUITO_QUENTE:
        achado("LARANJA", "N2", f"Muito quente: temperatura de {t:g} °C")
    elif t >= TEMP_QUENTE:
        achado("AMARELO", "N2", f"Quente: temperatura de {t:g} °C")
    elif t >= TEMP_FEBRICULA:
        achado("VERDE", "N2", f"Febrícula: temperatura de {t:g} °C")
    elif t <= TEMP_HIPOTERMIA_GRAVE:
        achado("VERMELHO", "N2", f"Hipotermia moderada: temperatura de {t:g} °C")
    elif t <= TEMP_HIPOTERMIA:
        achado("VERDE", "N2", f"Hipotermia leve: temperatura de {t:g} °C")

    # N3 — gestação [exceção obstétrica]
    if "gestante" in s:
        for cor, motivo, condicao in COMBINACOES_GESTACAO:
            if condicao(s, v):
                achado(cor, "N3", f"{motivo} (PA = {pa}) [exceção obstétrica]")

    # N4 — discriminadores dos fluxogramas (cor de cada sintoma e combinações do protocolo)
    urg = relatados(MUITO_URGENTES)
    if urg:
        achado("LARANJA", "N4", "Muito urgente: " + ", ".join(urg))
    for motivo, condicao in COMBINACOES_MUITO_URGENTES:
        if condicao(s, v):
            achado("LARANJA", "N4", motivo)
    mod = relatados(MODERADOS)
    if mod:
        achado("AMARELO", "N4", "Urgente: " + ", ".join(mod))
    for motivo, condicao in COMBINACOES_MODERADAS:
        if condicao(s, v):
            achado("AMARELO", "N4", motivo)
    leves = relatados(LEVES)
    if leves:
        achado("VERDE", "N4", "Pouco urgente (evento recente): " + ", ".join(leves))
    minimos = relatados(MINIMOS)
    if minimos:
        achado("AZUL", "N4", "Não urgente: " + ", ".join(minimos))

    # N6 — nenhum discriminador
    achado("AZUL", "N6", "Sinais vitais normais e sem discriminadores de urgência")

    principal = min(achados, key=lambda a: ORDEM_CORES.index(a["cor"]))  # empate: o primeiro da árvore
    # N5 — duração: o que daria verde, mas começou há mais de 7 dias sem piorar, é azul
    if principal["cor"] == "VERDE" and "queixa_antiga" in s:
        achado("AZUL", "N5", "Problema há mais de 7 dias, sem sinais de urgência (era verde: "
               + principal["motivo"] + ")")
        principal = achados[-1]
    outros = [a for a in achados if a is not principal and a["nivel"] != "N6"]
    return {
        "cor": principal["cor"],
        **CLASSES[principal["cor"]],
        "nivel": principal["nivel"],
        "motivo": principal["motivo"],
        "outros_achados": outros,
        "atendimento_prioritario": bool(motivos_prioridade),
        "motivos_prioridade": motivos_prioridade,
        "observacoes": observacoes,
        "news2": {"total": total, "pontos": pts, "informativo": True},  # não decide a cor
        "dados": {"vitais": {**v, "pulso_irregular": pulso_irregular}, "sintomas": sorted(s),
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
            "pulso_irregular": {"type": "boolean",
                                "description": "O medidor de pressão avisou batimento irregular"},
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
