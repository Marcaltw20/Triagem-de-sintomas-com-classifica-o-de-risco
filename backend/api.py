"""
API que comunica o front-end (React) com o backend.

Todas as rotas ficam aqui, sob o prefixo /api. Os formatos de entrada e saída estão em
schemas.py e a documentação de cada rota está em ../API.md.

  GET  /api/config        -> configurações da tela e nomes dos sintomas
  POST /api/transcrever   -> áudio do microfone -> texto (modo clássico)
  POST /api/chat          -> conversa com a LLM; quando terminar, devolve os sintomas (modo clássico)
  POST /api/falar         -> registra o texto a falar e devolve um id (modo clássico)
  GET  /api/falar/{id}    -> áudio MP3 em streaming (modo clássico)
  POST /api/realtime      -> chave temporária para o modo tempo real (voz -> voz via WebRTC)
  POST /api/pressao       -> espera a medição do Omron (até tempo_pressao_s)
  POST /api/spo2/iniciar  -> começa a esperar a saturação do relógio (no modo de teste, simula)
  GET  /api/spo2/ultima   -> última saturação recebida do relógio
  POST /api/classificar   -> envia sintomas + sinais vitais para a árvore e a LLM explica

  Tela de configuração (só administradores: cabeçalho "Authorization: Bearer <token>" do /api/login):
  POST   /api/login                  -> e-mail e senha de um usuário ADMIN do banco -> token
  POST   /api/logout                 -> encerra a sessão
  GET    /api/usuarios               -> usuários cadastrados
  POST   /api/usuarios               -> cadastra um usuário
  PATCH  /api/usuarios/{id}          -> bloqueia ou desbloqueia
  GET    /api/ajustes                -> ajustes atuais (modo de teste, medidores, tempos)
  PUT    /api/ajustes                -> altera os ajustes
  GET    /api/medidores/procurar     -> procura medidores Omron por perto (Bluetooth)
  POST   /api/medidores              -> cadastra um medidor de pressão
  POST   /api/medidores/{id}/parear  -> pareia o medidor (programa a chave)
  DELETE /api/medidores/{id}         -> remove o medidor

  Câmera (presenca.py): mesma pessoa do começo ao fim da triagem
  POST   /api/presenca/iniciar       -> liga a câmera; o primeiro rosto vira o titular da triagem
  GET    /api/presenca               -> presente / ausente / cancelada (o front consulta a cada 1 s)
  POST   /api/presenca/encerrar      -> desliga a câmera (fim da triagem)
  POST   /api/presenca/simular       -> modo de teste: sair / voltar / trocar (só administradores)
  GET    /api/camera/testar          -> a câmera abre? quantos rostos vê? (só administradores)
  POST   /api/triagens/cancelada     -> grava a triagem cancelada no banco

  Banco de dados (MySQL do XAMPP, banco.py):
  GET    /api/banco                   -> conectado? quantas triagens?
  GET    /api/triagens                -> últimas triagens gravadas
  POST   /api/triagens/encaminhamento -> grava quem foi encaminhado direto à enfermagem
  (as triagens concluídas são gravadas pela própria POST /api/classificar)

  Rota usada pelo app do relógio (sem o prefixo /api, igual ao antigo server.py do projeto-spo2):
  POST /spo2                         -> o Galaxy Watch envia {"spo2": 96, "timestamp": ms}
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

import ajustes
import autenticacao
import banco
import config
import llm
import presenca
import pressao
import spo2
from arvore_decisao import ROTULOS, DadosInvalidos, classificar_risco
from schemas import (CameraTesteOut, CancelamentoIn, PresencaOut, SimularPresencaIn, LoginIn, LoginOut, UsuarioAtivoIn, UsuarioIn, UsuarioOut, AjustesIn, AjustesOut, BancoEstadoOut, EncaminhamentoIn, EncaminhamentoOut,
                     TriagemResumo, ChatIn, ChatOut, ClassificarIn, ClassificarOut, ConfigOut,
                     FalarIn, FalarOut, Medidor, MedidorEncontrado, MedidorIn, PressaoOut, RealtimeIn,
                     RealtimeOut, Spo2InicioOut, Spo2RelogioIn, Spo2UltimaOut, TranscreverOut)

log = logging.getLogger("api")

router = APIRouter(prefix="/api")
relogio = APIRouter()  # rotas chamadas pelo app do Galaxy Watch
ADMIN = Depends(autenticacao.exigir_admin)  # rotas da tela de configuração


def _erro_openai(exc: Exception) -> HTTPException:
    log.exception("Erro na OpenAI")
    return HTTPException(status_code=502, detail=f"Erro na LLM: {exc}")


@router.get("/config", response_model=ConfigOut)
def obter_config():
    a = ajustes.ler()
    medidor = ajustes.medidor_ativo()
    return {
        "tempo_pressao_s": a["tempo_pressao_s"],
        "tempo_spo2_s": a["tempo_spo2_s"],
        "spo2": a["spo2"],
        "temp": a["temp"],
        "omron_simulado": a["modo_teste_pressao"],
        "spo2_simulado": a["modo_teste_spo2"],
        "usar_medidor": a["usar_medidor"] and medidor is not None,
        "usar_relogio": a["usar_relogio"],
        "medidor": medidor["nome"] if medidor else None,
        "usar_camera": a["usar_camera"],
        "camera_simulada": a["modo_teste_camera"],
        "tempo_abandono_s": a["tempo_abandono_s"],
        "modo_padrao": config.MODO_PADRAO,
        "silencio_ms": config.SILENCIO_MS,
        "nomes_sintomas": ROTULOS,
        "token_configurado": bool(config.OPENAI_API_KEY) and config.OPENAI_API_KEY != "coloque_seu_token_aqui",
    }


@router.post("/transcrever", response_model=TranscreverOut)
async def transcrever(audio: UploadFile = File(...)):
    dados = await audio.read()
    if len(dados) < 1000:
        return {"texto": ""}
    try:
        texto = await run_in_threadpool(llm.transcrever, dados, audio.filename or "fala.webm")
    except Exception as exc:  # noqa: BLE001
        raise _erro_openai(exc)
    return {"texto": texto}


@router.post("/chat", response_model=ChatOut)
async def chat(dados: ChatIn):
    try:
        perfil = dados.perfil.model_dump() if dados.perfil else None
        return await run_in_threadpool(llm.conversar, [m.model_dump() for m in dados.historico], perfil)
    except Exception as exc:  # noqa: BLE001
        raise _erro_openai(exc)


_falas: dict[str, str] = {}


@router.post("/falar", response_model=FalarOut)
def preparar_fala(dados: FalarIn):
    """Guarda o texto e devolve um id; o navegador toca GET /api/falar/{id} (áudio em streaming)."""
    if len(_falas) > 50:
        _falas.clear()
    id_fala = uuid.uuid4().hex
    _falas[id_fala] = dados.texto
    return {"id": id_fala}


@router.get("/falar/{id_fala}")
def falar(id_fala: str):
    texto = _falas.pop(id_fala, None)
    if texto is None:
        raise HTTPException(status_code=404, detail="Fala não encontrada")
    try:
        gerador = llm.falar_stream(texto)
        primeiro = next(gerador)  # garante que erros da OpenAI virem HTTP 502 (e não um áudio quebrado)
    except StopIteration:
        primeiro, gerador = b"", iter(())
    except Exception as exc:  # noqa: BLE001
        raise _erro_openai(exc)

    def corpo():
        yield primeiro
        yield from gerador

    return StreamingResponse(corpo(), media_type="audio/mpeg")


@router.post("/realtime", response_model=RealtimeOut)
async def sessao_realtime(dados: RealtimeIn | None = None):
    perfil = dados.perfil.model_dump() if dados and dados.perfil else None
    try:
        return await run_in_threadpool(llm.criar_sessao_realtime, perfil)
    except Exception as exc:  # noqa: BLE001
        raise _erro_openai(exc)


@router.post("/pressao", response_model=PressaoOut)
async def medir_pressao():
    try:
        # alguns segundos a mais que o cronômetro da tela, para dar tempo de baixar o registro
        return await pressao.medir_pressao(ajustes.ler()["tempo_pressao_s"] + 15)
    except (TimeoutError, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=408, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("Erro na leitura da pressão")
        raise HTTPException(status_code=500, detail=f"Erro no medidor de pressão: {exc}")


@router.post("/classificar", response_model=ClassificarOut)
async def classificar(dados: ClassificarIn):
    a = ajustes.ler()
    sat = dados.spo2 if dados.spo2 is not None else a["spo2"]
    temp = dados.temp if dados.temp is not None else a["temp"]
    try:
        perfil = dados.perfil.model_dump() if dados.perfil else {}
        resultado = classificar_risco(pas=dados.pas, pad=dados.pad, fc=dados.fc,
                                      spo2=sat, temp=temp, sintomas=dados.sintomas,
                                      pulso_irregular=dados.pulso_irregular, **perfil)
    except DadosInvalidos as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    triagem_id = None
    if dados.registro and a["salvar_no_banco"]:
        try:
            triagem_id = await run_in_threadpool(banco.salvar_triagem, dados.registro.model_dump(), perfil, resultado)
        except banco.BancoIndisponivel:
            log.warning("Triagem não gravada: banco de dados indisponível")
        except Exception:  # noqa: BLE001  (sem banco a triagem continua; só não fica gravada)
            log.exception("Não consegui gravar a triagem no banco")

    if not dados.explicar:
        return {"resultado": resultado, "texto": None, "triagem_id": triagem_id}
    try:
        texto = await run_in_threadpool(llm.explicar_resultado, resultado)
    except Exception:  # noqa: BLE001
        log.exception("LLM falhou ao explicar; usando texto padrão")
        texto = llm.texto_padrao_resultado(resultado)
    return {"resultado": resultado, "texto": texto, "triagem_id": triagem_id}


# --------------------------------------------------------------------------- #
# Saturação (SpO2) do Galaxy Watch
# --------------------------------------------------------------------------- #

@relogio.post("/spo2", status_code=201)
def receber_spo2_relogio(dados: Spo2RelogioIn):
    """Chamada pelo app do relógio (SpO2Uploader.kt) a cada medição concluída."""
    spo2.registrar(dados.spo2, dados.timestamp)
    return {"received": True}


@relogio.get("/health")
def saude():
    return {"status": "ok"}


@router.post("/spo2/iniciar", response_model=Spo2InicioOut)
async def iniciar_spo2():
    simulado = ajustes.ler()["modo_teste_spo2"]
    return {"inicio_ms": spo2.iniciar(simulado), "simulado": simulado}


@router.get("/spo2/ultima", response_model=Spo2UltimaOut)
def ultima_spo2():
    return {"leitura": spo2.ultima()}


# --------------------------------------------------------------------------- #
# Tela de configuração
# --------------------------------------------------------------------------- #

@router.post("/login", response_model=LoginOut)
async def entrar(dados: LoginIn):
    try:
        return await run_in_threadpool(autenticacao.verificar_login, dados.email, dados.senha)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:  # noqa: BLE001  (MySQL desligado, por exemplo)
        log.warning("Login indisponível: %s", exc)
        raise HTTPException(status_code=503, detail="Não consegui consultar os usuários: o banco de dados "
                                                    "(MySQL do XAMPP) está ligado?")


@router.post("/logout", status_code=204)
def sair(authorization: str | None = Header(default=None)):
    autenticacao.encerrar((authorization or "").removeprefix("Bearer ").strip())


def _ajustes_completos() -> dict:
    return {**ajustes.ler(), "modelos": ajustes.MODELOS, "url_relogio": f"http://{spo2.ip_local()}:8000/spo2"}


@router.get("/ajustes", response_model=AjustesOut, dependencies=[ADMIN])
def obter_ajustes():
    return _ajustes_completos()


@router.put("/ajustes", response_model=AjustesOut, dependencies=[ADMIN])
def alterar_ajustes(dados: AjustesIn):
    mudancas = dados.model_dump(exclude_unset=True)
    if "medidor_ativo" in mudancas and not any(m["id"] == mudancas["medidor_ativo"]
                                               for m in ajustes.ler()["medidores"]):
        raise HTTPException(status_code=404, detail="Medidor não encontrado")
    ajustes.atualizar(mudancas)
    return _ajustes_completos()


@router.get("/medidores/procurar", response_model=list[MedidorEncontrado], dependencies=[ADMIN])
async def procurar_medidores():
    try:
        return await pressao.procurar_medidores()
    except Exception as exc:  # noqa: BLE001
        log.exception("Erro ao procurar medidores")
        raise HTTPException(status_code=500, detail=f"Não consegui usar o Bluetooth: {exc}")


@router.post("/medidores", response_model=Medidor, status_code=201, dependencies=[ADMIN])
def cadastrar_medidor(dados: MedidorIn):
    if dados.modelo not in ajustes.MODELOS:
        raise HTTPException(status_code=422, detail="Modelo de medidor desconhecido")
    medidor = ajustes.novo_medidor(dados.nome, dados.modelo, dados.endereco)
    banco.sincronizar_dispositivos()
    return medidor


@router.post("/medidores/{id_medidor}/parear", response_model=Medidor, dependencies=[ADMIN])
async def parear_medidor(id_medidor: str):
    medidor = next((m for m in ajustes.ler()["medidores"] if m["id"] == id_medidor), None)
    if medidor is None:
        raise HTTPException(status_code=404, detail="Medidor não encontrado")
    try:
        endereco = await pressao.parear(medidor)
    except (TimeoutError, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=408, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("Erro ao parear o medidor")
        raise HTTPException(status_code=500, detail=f"Não consegui parear: {exc}")
    medidor = ajustes.alterar_medidor(id_medidor, pareado=True, endereco=endereco)
    banco.sincronizar_dispositivos()
    return medidor


@router.delete("/medidores/{id_medidor}", response_model=AjustesOut, dependencies=[ADMIN])
def remover_medidor(id_medidor: str):
    ajustes.remover_medidor(id_medidor)
    return _ajustes_completos()


# --------------------------------------------------------------------------- #
# Banco de dados
# --------------------------------------------------------------------------- #

@router.get("/banco", response_model=BancoEstadoOut, dependencies=[ADMIN])
async def estado_banco():
    return {**await run_in_threadpool(banco.estado), "salvar_no_banco": ajustes.ler()["salvar_no_banco"]}


@router.get("/triagens", response_model=list[TriagemResumo], dependencies=[ADMIN])
async def ultimas_triagens(limite: int = 10):
    try:
        return await run_in_threadpool(banco.ultimas_triagens, max(1, min(limite, 100)))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Banco de dados indisponível: {exc}")


@router.post("/triagens/encaminhamento", response_model=EncaminhamentoOut)
async def gravar_encaminhamento(dados: EncaminhamentoIn):
    if not ajustes.ler()["salvar_no_banco"]:
        return {"triagem_id": None}
    perfil = dados.perfil.model_dump() if dados.perfil else {}
    try:
        return {"triagem_id": await run_in_threadpool(banco.salvar_encaminhamento,
                                                      dados.paciente.model_dump(), perfil, dados.motivos)}
    except banco.BancoIndisponivel:
        log.warning("Encaminhamento não gravado: banco de dados indisponível")
    except Exception:  # noqa: BLE001
        log.exception("Não consegui gravar o encaminhamento no banco")
        return {"triagem_id": None}


# --------------------------------------------------------------------------- #
# Usuários (só administradores)
# --------------------------------------------------------------------------- #

def _banco_fora(exc: Exception) -> HTTPException:
    log.warning("Banco indisponível: %s", exc)
    return HTTPException(status_code=503, detail="Banco de dados indisponível. O MySQL está ligado no XAMPP?")


@router.get("/usuarios", response_model=list[UsuarioOut], dependencies=[ADMIN])
async def listar_usuarios():
    try:
        return await run_in_threadpool(banco.listar_usuarios)
    except Exception as exc:  # noqa: BLE001
        raise _banco_fora(exc)


@router.post("/usuarios", response_model=UsuarioOut, status_code=201, dependencies=[ADMIN])
async def cadastrar_usuario(dados: UsuarioIn):
    try:
        await run_in_threadpool(banco.criar_usuario, dados.nome, dados.email,
                                autenticacao.gerar_hash(dados.senha), dados.perfil)
        usuarios = await run_in_threadpool(banco.listar_usuarios)
    except banco.EmailEmUso as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise _banco_fora(exc)
    return next(u for u in usuarios if u["email"] == dados.email.strip().lower())


@router.patch("/usuarios/{id_usuario}", response_model=UsuarioOut)
async def bloquear_desbloquear(id_usuario: int, dados: UsuarioAtivoIn, sessao: dict = ADMIN):
    try:
        alvo = await run_in_threadpool(banco.buscar_usuario_por_id, id_usuario)
        if alvo is None:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        if not dados.ativo:
            if id_usuario == sessao["id"]:
                raise HTTPException(status_code=409, detail="Você não pode bloquear o seu próprio usuário.")
            if alvo["perfil"] == "ADMIN" and alvo["ativo"] and await run_in_threadpool(banco.contar_admins_ativos) <= 1:
                raise HTTPException(status_code=409, detail="Este é o último administrador ativo; não dá para bloqueá-lo.")
        await run_in_threadpool(banco.definir_ativo, id_usuario, dados.ativo)
        usuarios = await run_in_threadpool(banco.listar_usuarios)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _banco_fora(exc)
    if not dados.ativo:
        autenticacao.encerrar_do_usuario(id_usuario)  # quem estava logado sai na hora
    return next(u for u in usuarios if u["id"] == id_usuario)


# --------------------------------------------------------------------------- #
# Câmera: mesma pessoa do começo ao fim da triagem
# --------------------------------------------------------------------------- #

@router.post("/presenca/iniciar", response_model=PresencaOut)
async def iniciar_presenca():
    return await run_in_threadpool(presenca.iniciar)


@router.get("/presenca", response_model=PresencaOut)
def estado_presenca():
    return presenca.estado()


@router.post("/presenca/encerrar", status_code=204)
def encerrar_presenca():
    presenca.encerrar()


@router.post("/presenca/simular", response_model=PresencaOut, dependencies=[ADMIN])
def simular_presenca(dados: SimularPresencaIn):
    try:
        return presenca.simular(dados.evento)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/camera/testar", response_model=CameraTesteOut, dependencies=[ADMIN])
async def testar_camera(indice: int = 0):
    return await run_in_threadpool(presenca.testar_camera, indice)


@router.post("/triagens/cancelada", response_model=EncaminhamentoOut)
async def gravar_cancelamento(dados: CancelamentoIn):
    if not ajustes.ler()["salvar_no_banco"]:
        return {"triagem_id": None}
    perfil = dados.perfil.model_dump() if dados.perfil else {}
    try:
        return {"triagem_id": await run_in_threadpool(banco.salvar_cancelamento,
                                                      dados.paciente.model_dump(), perfil, dados.motivo)}
    except banco.BancoIndisponivel:
        log.warning("Cancelamento não gravado: banco de dados indisponível")
    except Exception:  # noqa: BLE001
        log.exception("Não consegui gravar o cancelamento no banco")
    return {"triagem_id": None}
