"""
Vigia de presença: confere pela câmera se quem está na frente do totem é a mesma pessoa que
começou a triagem. Usa o Reidentificador de ../reidentificacao/reidentificacao.py (rosto com YuNet,
assinatura facial com SFace).

Fluxo de uma triagem:
  iniciar()   liga a câmera numa thread; o primeiro rosto que aparecer (o maior, se houver
              mais de um) vira o TITULAR da triagem
  estado()    o front-end consulta a cada segundo:
                aguardando_rosto  ainda não viu ninguém
                presente          o titular está na frente da câmera
                ausente           o titular saiu (a tela pede para ele voltar)
                cancelada         outra pessoa ficou no lugar do titular -> triagem cancelada
                erro              câmera não abriu (a triagem segue sem vigia)
                desligado         câmera desligada na configuração, ou nenhuma triagem em curso
  encerrar()  desliga a câmera (fim da triagem)

Regras de cancelamento:
  - TROCA: o titular não está na frente E há outro rosto, claramente diferente do titular
    (similaridade < LIMIAR_DIFERENTE), por `tempo_troca_s` segundos seguidos. Um acompanhante
    ao lado do titular não cancela nada, e um rosto "parecido demais" (o titular voltando com
    outra luz, por exemplo) também não.
  - ABANDONO: o titular ficou fora da câmera por `tempo_abandono_s` segundos (padrão 10; 0 = nunca).
    A tela mostra a contagem regressiva enquanto ele está fora.

Nenhuma imagem é gravada: as assinaturas faciais ficam só na memória, durante a triagem.
No modo de teste (sem câmera), `simular()` faz o papel da câmera.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

import ajustes
import config  # noqa: F401  (coloca ../reidentificacao no sys.path)

log = logging.getLogger("presenca")

LIMIAR_DIFERENTE = 0.30   # abaixo disto o rosto é com certeza de outra pessoa
TAMANHO_MIN_ROSTO = 60    # px; rosto menor = assinatura pouco confiável (mesmo valor do script)
CONFIANCA_DETECCAO = 0.85
INTERVALO_QUADROS_S = 0.08  # ~12 quadros por segundo bastam e poupam a CPU do totem
MEMORIA_S = 3600            # o titular nunca é esquecido durante a triagem


class _Sessao:
    def __init__(self, simulada: bool):
        self.id = uuid.uuid4().hex[:12]
        self.simulada = simulada
        self.estado = "aguardando_rosto"
        self.mensagem = ""
        self.titular_id: int | None = None
        self.titular_presente = False
        self.ausente_desde: float | None = None
        self.troca_desde: float | None = None
        self.motivo_cancelamento: str | None = None
        self.parar = threading.Event()
        self.thread: threading.Thread | None = None
        # só no modo de teste
        self.sim_outro = False


_trava = threading.Lock()
_sessao: _Sessao | None = None
_modelos = None  # (detector, reconhecedor), carregados uma vez


# --------------------------------------------------------------------------- #
# Regras (valem para a câmera e para a simulação)
# --------------------------------------------------------------------------- #

def _avaliar(s: _Sessao, titular_presente: bool, outro_diferente: bool, agora: float,
             visto_por_ultimo: float | None = None) -> None:
    """Atualiza o estado da sessão a partir do que a câmera viu neste instante.
    `visto_por_ultimo`: quando a câmera viu o titular pela última vez (a ausência conta dali)."""
    a = ajustes.ler()
    if s.estado == "cancelada":
        return
    if titular_presente:
        s.ausente_desde = None
        s.troca_desde = None
        s.estado, s.mensagem = "presente", ""
        return

    s.ausente_desde = s.ausente_desde or visto_por_ultimo or agora
    s.estado, s.mensagem = "ausente", "Volte para a frente do totem para continuar a triagem."

    if outro_diferente:
        s.troca_desde = s.troca_desde or agora
        if agora - s.troca_desde >= a["tempo_troca_s"]:
            _cancelar(s, "Outra pessoa ficou na frente do totem no lugar de quem começou a triagem.")
            return
    else:
        s.troca_desde = None

    abandono = a["tempo_abandono_s"]
    if abandono and agora - s.ausente_desde >= abandono:
        _cancelar(s, f"A pessoa que começou a triagem ficou {abandono} segundos sem aparecer na frente do totem.")


def _cancelar(s: _Sessao, motivo: str) -> None:
    s.estado, s.motivo_cancelamento, s.mensagem = "cancelada", motivo, motivo
    s.parar.set()
    log.warning("Triagem cancelada pela câmera: %s", motivo)


# --------------------------------------------------------------------------- #
# Câmera
# --------------------------------------------------------------------------- #

def _carregar_modelos():
    global _modelos
    if _modelos is None:
        import cv2
        from reidentificacao import MODELOS, baixar_modelo

        det = baixar_modelo(*MODELOS["detector"])
        rec = baixar_modelo(*MODELOS["reconhecedor"])
        _modelos = (cv2.FaceDetectorYN.create(str(det), "", (320, 320), CONFIANCA_DETECCAO, 0.3, 5000),
                    cv2.FaceRecognizerSF.create(str(rec), ""))
    return _modelos


def _abrir_camera(indice: int):
    import cv2

    cap = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(indice)
    return cap


def _vigiar(s: _Sessao) -> None:
    import numpy as np
    from reidentificacao import Reidentificador

    a = ajustes.ler()
    cap = None
    try:
        detector, reconhecedor = _carregar_modelos()
        cap = _abrir_camera(a["camera_indice"])
        if not cap.isOpened():
            raise RuntimeError(f"não consegui abrir a câmera {a['camera_indice']}")
        reid = Reidentificador(a["limiar_camera"], ausencia=1.0, memoria=MEMORIA_S, arquivo_log=None)
        log.info("Câmera %s ligada para a triagem %s", a["camera_indice"], s.id)

        while not s.parar.is_set():
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("a câmera parou de enviar imagens")
            agora = time.time()
            h, w = frame.shape[:2]
            detector.setInputSize((w, h))
            _, faces = detector.detect(frame)

            deteccoes = []
            for f in (faces if faces is not None else []):
                x, y, fw, fh = f[:4].astype(int)
                if fw < TAMANHO_MIN_ROSTO:
                    continue
                emb = reconhecedor.feature(reconhecedor.alignCrop(frame, f)).flatten()
                deteccoes.append(((max(x, 0), max(y, 0), fw, fh), emb / (np.linalg.norm(emb) + 1e-9)))
            resultado = reid.atualizar(deteccoes, agora)

            with _trava:
                if s.titular_id is None:
                    if resultado:  # o maior rosto (o mais perto) vira o titular
                        titular, _ = max(resultado, key=lambda r: r[0].caixa[2] * r[0].caixa[3])
                        s.titular_id = titular.id
                        log.info("Titular da triagem %s: pessoa #%s", s.id, titular.id)
                    else:
                        time.sleep(INTERVALO_QUADROS_S)
                        continue
                titular = next((p for p in reid.pessoas if p.id == s.titular_id), None)
                titular_presente = bool(titular and titular.presente)
                outro_diferente = bool(titular) and any(
                    p.id != s.titular_id and titular.similaridade(emb) < LIMIAR_DIFERENTE
                    for (p, _), (_, emb) in zip(resultado, deteccoes))
                _avaliar(s, titular_presente, outro_diferente, agora, titular.ultima_vez if titular else None)
            time.sleep(INTERVALO_QUADROS_S)
    except Exception as exc:  # noqa: BLE001  (sem câmera a triagem continua, só sem vigia)
        log.warning("Vigia de presença desligado: %s", exc)
        with _trava:
            if s.estado != "cancelada":
                s.estado, s.mensagem = "erro", f"Câmera indisponível: {exc}"
    finally:
        if cap is not None:
            cap.release()
        log.info("Câmera desligada (triagem %s)", s.id)


# --------------------------------------------------------------------------- #
# Interface usada pela API
# --------------------------------------------------------------------------- #

def iniciar() -> dict[str, Any]:
    """Começa a vigiar uma nova triagem (encerra a anterior, se houver)."""
    global _sessao
    encerrar()
    a = ajustes.ler()
    if not a["usar_camera"]:
        return {"sessao": None, "estado": "desligado", "mensagem": "", "simulado": False, "ausente_s": 0}
    s = _Sessao(simulada=a["modo_teste_camera"])
    with _trava:
        _sessao = s
        if s.simulada:
            s.titular_id, s.estado = 1, "presente"
            s.titular_presente = True
    if not s.simulada:
        s.thread = threading.Thread(target=_vigiar, args=(s,), name="vigia-presenca", daemon=True)
        s.thread.start()
    return estado()


def estado() -> dict[str, Any]:
    with _trava:
        s = _sessao
        if s is None:
            return {"sessao": None, "estado": "desligado", "mensagem": "", "simulado": False, "ausente_s": 0}
        if s.simulada:  # na simulação o tempo também conta, igual à câmera
            _avaliar(s, s.titular_presente, s.sim_outro, time.time())
        ausente = round(time.time() - s.ausente_desde) if s.ausente_desde and s.estado == "ausente" else 0
        return {"sessao": s.id, "estado": s.estado, "mensagem": s.mensagem, "simulado": s.simulada,
                "ausente_s": ausente}


def encerrar() -> None:
    global _sessao
    with _trava:
        s, _sessao = _sessao, None
    if s:
        s.parar.set()


def simular(evento: str) -> dict[str, Any]:
    """Modo de teste: 'sair' (titular sai), 'voltar' (titular volta), 'trocar' (outra pessoa no lugar)."""
    with _trava:
        s = _sessao
        if s is None or not s.simulada:
            raise RuntimeError("Não há triagem com a câmera simulada em andamento.")
        if evento == "voltar":
            s.titular_presente, s.sim_outro = True, False
        elif evento == "sair":
            s.titular_presente, s.sim_outro = False, False
        elif evento == "trocar":
            s.titular_presente, s.sim_outro = False, True
        else:
            raise ValueError(evento)
    return estado()


def testar_camera(indice: int) -> dict[str, Any]:
    """Tela de configuração: a câmera abre? Quantos rostos ela vê agora? (nenhuma imagem é guardada)"""
    if _sessao is not None and not _sessao.simulada:
        return {"ok": False, "mensagem": "A câmera está em uso por uma triagem agora.", "rostos": None}
    try:
        detector, _ = _carregar_modelos()
        cap = _abrir_camera(indice)
        try:
            if not cap.isOpened():
                return {"ok": False, "mensagem": f"Não consegui abrir a câmera {indice}.", "rostos": None}
            for _ in range(5):  # os primeiros quadros costumam vir escuros
                ok, frame = cap.read()
            if not ok:
                return {"ok": False, "mensagem": "A câmera abriu, mas não enviou imagem.", "rostos": None}
            h, w = frame.shape[:2]
            detector.setInputSize((w, h))
            _, faces = detector.detect(frame)
            n = 0 if faces is None else int(sum(1 for f in faces if f[2] >= TAMANHO_MIN_ROSTO))
            return {"ok": True, "mensagem": f"Câmera {indice} funcionando ({w}x{h}).", "rostos": n}
        finally:
            cap.release()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "mensagem": f"Erro na câmera: {exc}", "rostos": None}

