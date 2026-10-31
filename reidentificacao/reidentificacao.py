"""
Reidentificação de pessoas pela webcam.

Detecta rostos (YuNet), extrai uma assinatura facial (SFace) e mantém uma
"memória" das pessoas vistas. Quando alguém sai da frente da câmera e volta,
o programa diz se é a MESMA pessoa (e há quanto tempo ela tinha saído) ou
uma pessoa NOVA.

Uso:
    python reidentificacao.py                  # webcam 0
    python reidentificacao.py --camera 1       # outra webcam
    python reidentificacao.py --video arq.mp4  # arquivo de vídeo
    python reidentificacao.py --limiar 0.45 --ausencia 1.5 --memoria 120

Teclas: q / ESC = sair | r = limpar memória
"""

import argparse
import csv
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

PASTA = Path(__file__).resolve().parent
PASTA_MODELOS = PASTA / "modelos"
MODELOS = {
    "detector": (
        "face_detection_yunet_2023mar.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ),
    "reconhecedor": (
        "face_recognition_sface_2021dec.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ),
}

CORES = [(0, 200, 0), (255, 128, 0), (0, 128, 255), (200, 0, 200),
         (0, 200, 200), (128, 0, 255), (255, 0, 128), (128, 128, 0)]


def baixar_modelo(nome: str, url: str) -> Path:
    PASTA_MODELOS.mkdir(exist_ok=True)
    caminho = PASTA_MODELOS / nome
    if not caminho.exists() or caminho.stat().st_size < 10_000:
        print(f"Baixando modelo {nome} ...")
        urllib.request.urlretrieve(url, caminho)
    return caminho


@dataclass
class Pessoa:
    id: int
    assinaturas: list            # embeddings normalizados (np.ndarray 128-d)
    primeira_vez: float
    ultima_vez: float
    visitas: int = 1
    presente: bool = True
    mensagem: str = ""
    mensagem_ate: float = 0.0
    caixa: tuple = field(default=(0, 0, 0, 0))

    def similaridade(self, emb: np.ndarray) -> float:
        # Similaridade de cosseno com a melhor assinatura guardada
        return float(max(np.dot(a, emb) for a in self.assinaturas))

    def adicionar_assinatura(self, emb: np.ndarray, maximo: int) -> None:
        # Guarda assinaturas variadas (poses/iluminação diferentes)
        if self.similaridade(emb) < 0.85:
            self.assinaturas.append(emb)
            if len(self.assinaturas) > maximo:
                self.assinaturas.pop(1)  # mantém sempre a primeira


class Reidentificador:
    def __init__(self, limiar: float, ausencia: float, memoria: float,
                 max_assinaturas: int = 10, arquivo_log: Path | None = None):
        self.limiar = limiar          # similaridade mínima p/ ser a mesma pessoa
        self.ausencia = ausencia      # segundos sem aparecer = "saiu da frente"
        self.memoria = memoria        # segundos até esquecer a pessoa
        self.max_assinaturas = max_assinaturas
        self.pessoas: list[Pessoa] = []
        self.proximo_id = 1
        self.arquivo_log = arquivo_log
        if arquivo_log and not arquivo_log.exists():
            with open(arquivo_log, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["data_hora", "evento", "pessoa_id",
                                        "tempo_fora_s", "similaridade"])

    def _log(self, evento: str, pid: int, tempo_fora: float = 0.0, sim: float = 0.0):
        agora = datetime.now().strftime("%H:%M:%S")
        if evento == "NOVA":
            print(f"[{agora}] Nova pessoa detectada -> Pessoa #{pid}")
        elif evento == "VOLTOU":
            print(f"[{agora}] MESMA PESSOA: Pessoa #{pid} voltou após "
                  f"{tempo_fora:.1f}s fora (similaridade {sim:.2f})")
        elif evento == "SAIU":
            print(f"[{agora}] Pessoa #{pid} saiu da frente da câmera")
        elif evento == "ESQUECIDA":
            print(f"[{agora}] Pessoa #{pid} removida da memória")
        if self.arquivo_log:
            with open(self.arquivo_log, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"),
                                        evento, pid, f"{tempo_fora:.2f}", f"{sim:.3f}"])

    def atualizar(self, deteccoes: list[tuple[tuple, np.ndarray]], agora: float):
        """deteccoes: lista de (caixa, embedding). Retorna lista de (Pessoa, sim)."""
        # 1) Matriz de similaridade e associação gulosa (melhor par primeiro),
        #    garantindo que duas faces do mesmo quadro não virem a mesma pessoa.
        pares = []
        for i, (_, emb) in enumerate(deteccoes):
            for j, p in enumerate(self.pessoas):
                s = p.similaridade(emb)
                if s >= self.limiar:
                    pares.append((s, i, j))
        pares.sort(reverse=True)

        usadas_det, usadas_pes = set(), set()
        associacao = {}
        for s, i, j in pares:
            if i in usadas_det or j in usadas_pes:
                continue
            associacao[i] = (j, s)
            usadas_det.add(i)
            usadas_pes.add(j)

        resultado = []
        for i, (caixa, emb) in enumerate(deteccoes):
            if i in associacao:
                j, s = associacao[i]
                p = self.pessoas[j]
                if not p.presente:
                    tempo_fora = agora - p.ultima_vez
                    p.visitas += 1
                    p.presente = True
                    p.mensagem = f"MESMA PESSOA! voltou apos {tempo_fora:.1f}s"
                    p.mensagem_ate = agora + 3.0
                    self._log("VOLTOU", p.id, tempo_fora, s)
                p.ultima_vez = agora
                p.caixa = caixa
                p.adicionar_assinatura(emb, self.max_assinaturas)
            else:
                p = Pessoa(self.proximo_id, [emb], agora, agora, caixa=caixa)
                p.mensagem = "Pessoa nova"
                p.mensagem_ate = agora + 2.0
                self.pessoas.append(p)
                self.proximo_id += 1
                s = 1.0
                self._log("NOVA", p.id)
            resultado.append((p, s))

        # 2) Quem sumiu por mais de `ausencia` segundos saiu da frente;
        #    quem sumiu por mais de `memoria` segundos é esquecido.
        for p in list(self.pessoas):
            fora = agora - p.ultima_vez
            if p.presente and fora > self.ausencia:
                p.presente = False
                self._log("SAIU", p.id)
            if not p.presente and fora > self.memoria:
                self.pessoas.remove(p)
                self._log("ESQUECIDA", p.id)
        return resultado

    def limpar(self):
        self.pessoas.clear()
        self.proximo_id = 1
        print("Memória limpa.")


def desenhar(frame, resultado, reid: Reidentificador, agora: float, fps: float):
    for p, sim in resultado:
        x, y, w, h = p.caixa
        cor = CORES[(p.id - 1) % len(CORES)]
        cv2.rectangle(frame, (x, y), (x + w, y + h), cor, 2)
        texto = f"Pessoa #{p.id}  sim={sim:.2f}  visitas={p.visitas}"
        cv2.rectangle(frame, (x, y - 24), (x + max(w, 10 * len(texto)), y), cor, -1)
        cv2.putText(frame, texto, (x + 4, y - 7), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)
        if agora < p.mensagem_ate:
            cv2.putText(frame, p.mensagem, (x, y + h + 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, cor, 2, cv2.LINE_AA)

    # Painel com as pessoas lembradas que não estão na tela
    ausentes = [p for p in reid.pessoas if not p.presente]
    linhas = [f"FPS: {fps:.1f}   Pessoas na memoria: {len(reid.pessoas)}"]
    for p in ausentes:
        linhas.append(f"#{p.id} fora ha {agora - p.ultima_vez:.1f}s")
    for k, linha in enumerate(linhas):
        cv2.putText(frame, linha, (10, 22 + 20 * k), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 255), 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description="Reidentificação de pessoas pela câmera")
    ap.add_argument("--camera", type=int, default=0, help="índice da webcam")
    ap.add_argument("--video", type=str, help="arquivo de vídeo (em vez da webcam)")
    ap.add_argument("--limiar", type=float, default=0.40,
                    help="similaridade de cosseno mínima p/ mesma pessoa (SFace: 0.363)")
    ap.add_argument("--ausencia", type=float, default=1.0,
                    help="segundos sem ver a pessoa para considerar que ela saiu")
    ap.add_argument("--memoria", type=float, default=300.0,
                    help="segundos que a pessoa fica na memória após sair")
    ap.add_argument("--confianca", type=float, default=0.85,
                    help="confiança mínima da detecção de rosto")
    ap.add_argument("--tamanho-min", type=int, default=60,
                    help="largura mínima do rosto (px) para reconhecer")
    ap.add_argument("--log", type=str, default="eventos.csv",
                    help="arquivo CSV de eventos ('' para desativar)")
    args = ap.parse_args()

    det_path = baixar_modelo(*MODELOS["detector"])
    rec_path = baixar_modelo(*MODELOS["reconhecedor"])

    detector = cv2.FaceDetectorYN.create(str(det_path), "", (320, 320),
                                         args.confianca, 0.3, 5000)
    reconhecedor = cv2.FaceRecognizerSF.create(str(rec_path), "")

    fonte = args.video if args.video else args.camera
    cap = cv2.VideoCapture(fonte, cv2.CAP_DSHOW) if not args.video else cv2.VideoCapture(fonte)
    if not cap.isOpened():
        cap = cv2.VideoCapture(fonte)
    if not cap.isOpened():
        raise SystemExit(f"Não foi possível abrir a fonte de vídeo: {fonte}")

    log = (PASTA / args.log) if args.log else None
    reid = Reidentificador(args.limiar, args.ausencia, args.memoria, arquivo_log=log)

    print("Pressione 'q' para sair, 'r' para limpar a memória.")
    t_anterior, fps = time.time(), 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        agora = time.time()
        h, w = frame.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(frame)

        deteccoes = []
        if faces is not None:
            for f in faces:
                x, y, fw, fh = f[:4].astype(int)
                if fw < args.tamanho_min:
                    continue  # rosto pequeno demais = assinatura pouco confiável
                alinhado = reconhecedor.alignCrop(frame, f)
                emb = reconhecedor.feature(alinhado).flatten()
                emb = emb / (np.linalg.norm(emb) + 1e-9)
                deteccoes.append(((max(x, 0), max(y, 0), fw, fh), emb))

        resultado = reid.atualizar(deteccoes, agora)

        dt = agora - t_anterior
        t_anterior = agora
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt)
        desenhar(frame, resultado, reid, agora, fps)

        cv2.imshow("Reidentificacao de pessoas", frame)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla in (ord("q"), 27):
            break
        if tecla == ord("r"):
            reid.limpar()

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
