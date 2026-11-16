"""
LLM (ChatGPT / OpenAI) da triagem.

Papel da LLM:
  1. Conversar com o usuário por voz e descobrir os sintomas.
  2. Quando tiver informação suficiente, chamar a ferramenta `registrar_sintomas`
     com as chaves exatas que a árvore de decisão entende.
  3. No final, explicar em voz a classificação que a ÁRVORE escolheu.

A LLM NÃO decide a cor — quem decide é `arvore_decisao.classificar_risco`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterator

from openai import OpenAI

import config
from arvore_decisao import CATALOGO, DEFICIENCIAS, IDADE_ADULTO, SEXOS, SINTOMAS

_cliente: OpenAI | None = None


def cliente() -> OpenAI:
    global _cliente
    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "coloque_seu_token_aqui":
        raise RuntimeError("Token da OpenAI não configurado. Coloque OPENAI_API_KEY no arquivo backend/.env")
    if _cliente is None:
        _cliente = OpenAI(api_key=config.OPENAI_API_KEY)
    return _cliente


# --------------------------------------------------------------------------- #
# Prompts e ferramenta
# --------------------------------------------------------------------------- #

LISTA_SINTOMAS = "\n".join(
    f"[{categoria}]\n" + "\n".join(f"- {k}: {d}" for k, _, d, _ in itens)
    for categoria, itens in CATALOGO.items()
)

PROMPT_CONVERSA = f"""Você é a assistente virtual de triagem de um totem de saúde. Você conversa
por VOZ com o usuário, em português do Brasil.

Seu objetivo é descobrir quais sintomas o usuário está sentindo agora.
Regras:
- Respostas curtas (1 a 2 frases), linguagem simples e acolhedora. Nada de listas, emojis ou markdown,
  pois o texto será falado.
- Faça UMA pergunta por vez. Para a queixa principal, esclareça o que muda a chave a registrar:
  intensidade (leve, moderada ou insuportável), se começou de repente, e os sintomas que costumam vir junto
  (ex.: dor no peito -> suor frio, enjoo, falta de ar, irradia para o braço; dor de cabeça -> pescoço duro,
  febre, visão alterada; vômito ou diarreia -> sangue, boca seca, tontura; pancada na cabeça -> vômito, confusão;
  sangramento -> se para ao apertar).
- Pergunte uma vez se a pessoa tem algum problema de saúde importante (diabetes, doença do coração, asma ou
  bronquite, imunidade baixa, remédio para afinar o sangue) e registre as chaves de "Fatores de risco" que se
  aplicarem. A idade já vem da identificação: não pergunte a idade e não registre `idoso`.
- Sobre gravidez, siga os "Dados da identificação" no fim destas instruções.
- Antes de encerrar, pergunte se há mais alguma coisa incomodando.
- Não dê diagnóstico, não indique remédios e NUNCA diga qual é a classificação de risco: quem classifica é
  o sistema, depois de medir a pressão.
- Assim que tiver informação suficiente (normalmente depois de 3 a 6 perguntas), ou se o usuário disser
  que não sente mais nada, chame a ferramenta `registrar_sintomas`.
- Se o usuário relatar algo muito grave (desmaio, confusão, convulsão, fraqueza em um lado do corpo, dor forte
  no peito, engasgo, garganta inchando, sangramento que não para), chame a ferramenta imediatamente.

Sintomas que o sistema entende, por categoria (use exatamente estas chaves):
{LISTA_SINTOMAS}

Como escolher as chaves:
- Registre TODAS as chaves que se aplicam, não só a queixa principal.
- Use a chave mais específica e só a intensidade que o usuário confirmou (ex.: `dor_toracica_intensa` apenas
  se a dor no peito for forte; `falta_de_ar_grave` apenas se não consegue completar uma frase).
- Não registre a versão leve e a grave do mesmo sintoma ao mesmo tempo.
- Só registre o que o usuário disse; não deduza sintomas.
- Se o usuário sentir algo que não se encaixa em nenhuma chave, use `outro_sintoma` (ou `dor_leve`,
  `dor_moderada`, `dor_intensa` se for uma dor).
- Se o usuário não sentir nada, chame a ferramenta com a lista vazia.
"""

FERRAMENTA_SINTOMAS = {
    "type": "function",
    "function": {
        "name": "registrar_sintomas",
        "description": "Registra os sintomas relatados pelo usuário para enviar à árvore de decisão. "
                       "Chame quando a entrevista de sintomas estiver concluída.",
        "parameters": {
            "type": "object",
            "properties": {
                "sintomas": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(SINTOMAS)},
                    "description": "Chaves de todos os sintomas e fatores de risco relatados "
                                   "(significados no prompt do sistema).",
                },
                "resumo": {
                    "type": "string",
                    "description": "Resumo curto, em uma frase, do que o usuário relatou.",
                },
            },
            "required": ["sintomas", "resumo"],
            "additionalProperties": False,
        },
    },
}

PROMPT_RESULTADO = """Você é a assistente virtual de triagem de um totem de saúde e fala por VOZ, em
português do Brasil. O sistema (árvore de decisão) já classificou o risco do usuário. Explique o resultado
ao usuário em 2 a 3 frases curtas, simples e calmas:
- diga a cor da classificação e a prioridade;
- explique de forma simples o motivo;
- diga a orientação (o que fazer agora);
- se "atendimento_prioritario" for verdadeiro, diga que a pessoa tem direito a atendimento prioritário.
Não mude a classificação, não invente dados e não use listas, emojis ou markdown."""


# --------------------------------------------------------------------------- #
# Funções usadas pelo servidor
# --------------------------------------------------------------------------- #

def contexto_paciente(perfil: dict[str, Any] | None) -> str:
    """Instruções sobre o paciente, vindas da identificação no totem (idade, sexo, deficiências).
    Vai no fim do prompt para não atrapalhar o cache do começo, que é sempre igual."""
    perfil = perfil or {}
    idade, sexo = perfil.get("idade"), perfil.get("sexo")
    deficiencias = perfil.get("deficiencias") or []
    linhas = []
    if idade is not None:
        linhas.append(f"- Idade: {idade} anos.")
    if sexo in SEXOS:
        linhas.append(f"- Sexo: {SEXOS[sexo]}.")

    if sexo == "M":
        linhas.append("- Não pergunte sobre gravidez e nunca registre `gestante`, `perda_liquido_contracoes`, "
                      "`bebe_mexendo_menos` ou `sangramento_vaginal`.")
    elif sexo == "F" and idade is not None and not (10 <= idade <= 55):
        linhas.append("- Não pergunte sobre gravidez.")
    else:
        linhas.append("- Pergunte uma vez se a pessoa está ou pode estar grávida; se sim, registre `gestante`.")
    if sexo == "F":
        linhas.append("- Nunca registre `dor_testicular_subita`.")
    if idade is not None and idade < IDADE_ADULTO:
        linhas.append("- É uma criança ou adolescente: use palavras simples e pergunte se há um responsável junto, "
                      "que pode ajudar a responder.")

    for d in deficiencias:
        if d == "visual":
            linhas.append("- Tem deficiência visual: não peça para olhar ou ler a tela; diga em voz alta as opções "
                          "de resposta quando fizer uma pergunta de escolha.")
        elif d == "auditiva":
            linhas.append("- Tem deficiência auditiva: a pessoa deve estar lendo e escrevendo; use frases curtas e "
                          "diretas, sem depender do tom de voz.")
        elif d == "fisica":
            linhas.append("- Tem deficiência física: não peça para a pessoa fazer movimentos ou testes com o corpo.")
        elif d == "intelectual":
            linhas.append("- Tem deficiência intelectual ou mental: use frases bem curtas e simples, uma ideia por "
                          "vez, confirme se a pessoa entendeu e aceite respostas de um acompanhante.")
    if deficiencias:
        nomes = ", ".join(DEFICIENCIAS[d].lower() for d in deficiencias if d in DEFICIENCIAS)
        linhas.append(f"- Não registre a deficiência como sintoma ({nomes}): ela já foi informada ao sistema.")

    return "\n\nDados da identificação (já informados; não pergunte de novo):\n" + "\n".join(linhas)


def conversar(historico: list[dict[str, str]], perfil: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Recebe o histórico [{role: "user"|"assistant", content: "..."}] e devolve:
      {"texto": "...", "sintomas_concluidos": bool, "sintomas": [...], "resumo": "..."}
    """
    mensagens = [{"role": "system", "content": PROMPT_CONVERSA + contexto_paciente(perfil)}, *historico]
    resp = cliente().chat.completions.create(
        model=config.MODELO_CHAT,
        messages=mensagens,
        tools=[FERRAMENTA_SINTOMAS],
        temperature=0.3,
        max_tokens=300,  # folga para a chamada da ferramenta com várias chaves + resumo
    )
    msg = resp.choices[0].message

    chamada = next((c for c in (msg.tool_calls or []) if c.function.name == "registrar_sintomas"), None)
    if chamada is None:
        return {"texto": msg.content or "", "sintomas_concluidos": False, "sintomas": [], "resumo": ""}

    args = json.loads(chamada.function.arguments or "{}")
    sintomas = [s for s in args.get("sintomas", []) if s in SINTOMAS]
    resumo = args.get("resumo", "")

    # Fala de transição fixa (sem 2ª chamada à LLM = resposta mais rápida)
    texto = texto_transicao_pressao()
    return {"texto": texto, "sintomas_concluidos": True, "sintomas": sintomas, "resumo": resumo}


def texto_transicao_pressao() -> str:
    return ("Obrigada, anotei seus sintomas. Agora vamos medir sua pressão: coloque a braçadeira no braço "
            "esquerdo, fique sentado, parado e em silêncio, e aperte o botão iniciar do medidor. "
            f"Você tem {config.TEMPO_PRESSAO_S} segundos.")


def resumo_resultado(resultado: dict[str, Any]) -> dict[str, Any]:
    """Só os campos que a LLM precisa para explicar (o resultado completo gasta tokens à toa)."""
    return {k: resultado[k] for k in ("cor", "prioridade", "motivo", "orientacao", "atendimento_prioritario")}


def explicar_resultado(resultado: dict[str, Any]) -> str:
    """Gera a fala explicando a classificação que a árvore escolheu."""
    resp = cliente().chat.completions.create(
        model=config.MODELO_CHAT,
        messages=[
            {"role": "system", "content": PROMPT_RESULTADO},
            {"role": "user", "content": "Resultado da árvore de decisão:\n"
                                        + json.dumps(resumo_resultado(resultado), ensure_ascii=False)},
        ],
        temperature=0.3,
        max_tokens=150,
    )
    return resp.choices[0].message.content or texto_padrao_resultado(resultado)


# --------------------------------------------------------------------------- #
# Modo tempo real (OpenAI Realtime API): voz -> voz direto, via WebRTC no navegador
# --------------------------------------------------------------------------- #

PROMPT_REALTIME = PROMPT_CONVERSA + """
Fale em ritmo natural e um pouco rápido, com voz calma. Ao começar a conversa, cumprimente brevemente,
diga que vai fazer algumas perguntas e depois medir a pressão, e pergunte o que a pessoa está sentindo.
Depois de registrar os sintomas, siga exatamente o "proximo_passo" devolvido pela ferramenta.
Quando receber o resultado da árvore de decisão, apenas explique-o, sem mudar a classificação."""


def criar_sessao_realtime(perfil: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cria uma chave temporária (ephemeral) para o navegador conectar direto na Realtime API.
    O token de verdade nunca vai para o navegador."""
    import httpx

    cliente()  # valida se o token foi configurado
    f = FERRAMENTA_SINTOMAS["function"]
    sessao = {
        "type": "realtime",
        "model": config.MODELO_REALTIME,
        "instructions": PROMPT_REALTIME + contexto_paciente(perfil),
        "tools": [{"type": "function", "name": f["name"], "description": f["description"],
                   "parameters": f["parameters"]}],
        "tool_choice": "auto",
        "audio": {
            "input": {
                "transcription": {"model": config.MODELO_TRANSCRICAO, "language": "pt"},
                "noise_reduction": {"type": "near_field"},
                "turn_detection": {"type": "server_vad", "silence_duration_ms": config.SILENCIO_MS,
                                   "prefix_padding_ms": 300, "threshold": 0.5},
            },
            "output": {"voice": config.VOZ_REALTIME},
        },
    }
    r = httpx.post(
        "https://api.openai.com/v1/realtime/client_secrets",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={"session": sessao},
        timeout=20,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Realtime API {r.status_code}: {r.text}")
    return {"chave": r.json()["value"], "modelo": config.MODELO_REALTIME,
            "texto_transicao": texto_transicao_pressao(), "prompt_resultado": PROMPT_RESULTADO}


def texto_padrao_resultado(r: dict[str, Any]) -> str:
    """Fala de reserva (sem LLM) caso a OpenAI falhe."""
    return (f"Sua classificação é {r['cor'].lower()}, prioridade {r['prioridade'].lower()}. "
            f"Motivo: {r['motivo']}. {r['orientacao']}")


def transcrever(audio: bytes, nome_arquivo: str) -> str:
    """Áudio do microfone -> texto (speech-to-text)."""
    t = cliente().audio.transcriptions.create(
        model=config.MODELO_TRANSCRICAO,
        file=(nome_arquivo, audio),
        language="pt",
    )
    return (t.text or "").strip()


def falar_stream(texto: str) -> Iterator[bytes]:
    """Texto -> áudio MP3 em streaming (o navegador começa a tocar antes de terminar de gerar).
    Falas repetidas (saudação, instrução da pressão...) saem do cache em disco, sem chamar a OpenAI."""
    usar_cache = config.CACHE_VOZ_MAX > 0
    chave = hashlib.sha256(f"{config.MODELO_VOZ}|{config.VOZ}|{texto}".encode()).hexdigest()
    arquivo = config.PASTA_CACHE_VOZ / f"{chave}.mp3"
    if usar_cache and arquivo.exists():
        yield arquivo.read_bytes()
        return

    pedacos = []
    with cliente().audio.speech.with_streaming_response.create(
        model=config.MODELO_VOZ,
        voice=config.VOZ,
        input=texto,
        response_format="mp3",
    ) as resp:
        for pedaco in resp.iter_bytes(4096):
            pedacos.append(pedaco)
            yield pedaco

    if usar_cache:
        config.PASTA_CACHE_VOZ.mkdir(exist_ok=True)
        arquivo.write_bytes(b"".join(pedacos))
        antigos = sorted(config.PASTA_CACHE_VOZ.glob("*.mp3"), key=lambda a: a.stat().st_mtime)
        for a in antigos[:-config.CACHE_VOZ_MAX]:
            a.unlink(missing_ok=True)
