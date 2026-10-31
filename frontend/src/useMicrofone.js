import { useCallback, useRef, useState } from "react";

// Captação do microfone com detecção automática de fala:
// começa a gravar, percebe quando o usuário começou a falar e para sozinho
// depois de um tempo de silêncio. Devolve o áudio (Blob) ou null se ninguém falou.

const INTERVALO_MS = 50;

export function useMicrofone() {
  const streamRef = useRef(null);
  const pararRef = useRef(null);
  const [nivel, setNivel] = useState(0); // volume atual (0..1), para a animação
  const [gravando, setGravando] = useState(false);

  const garantirPermissao = useCallback(async () => {
    if (!streamRef.current || !streamRef.current.active) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    }
    return streamRef.current;
  }, []);

  const gravarFala = useCallback(
    async ({ silencioMs = 1500, maxMs = 30000, esperaMaxMs = 15000 } = {}) => {
      const stream = await garantirPermissao();

      const ctx = new AudioContext();
      const analisador = ctx.createAnalyser();
      analisador.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analisador);
      const amostras = new Float32Array(analisador.fftSize);

      const tipos = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
      const mimeType = tipos.find((t) => MediaRecorder.isTypeSupported(t));
      const gravador = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const partes = [];
      gravador.ondataavailable = (e) => e.data.size && partes.push(e.data);

      return new Promise((resolve) => {
        const inicio = performance.now();
        let ultimoSom = inicio;
        let falou = false;
        let ruido = 0.01; // nível do ruído ambiente (calibrado no começo)
        let n = 0;

        const finalizar = () => {
          if (gravador.state !== "inactive") gravador.stop();
        };
        pararRef.current = finalizar;

        gravador.onstop = () => {
          clearInterval(timer);
          ctx.close();
          pararRef.current = null;
          setNivel(0);
          setGravando(false);
          resolve(falou && partes.length ? new Blob(partes, { type: gravador.mimeType }) : null);
        };

        const timer = setInterval(() => {
          analisador.getFloatTimeDomainData(amostras);
          let soma = 0;
          for (const a of amostras) soma += a * a;
          const rms = Math.sqrt(soma / amostras.length);
          const agora = performance.now();
          setNivel(Math.min(1, rms * 8));

          // primeiros 400 ms: mede o ruído ambiente
          if (agora - inicio < 400) {
            ruido = (ruido * n + rms) / ++n;
            return;
          }
          const limiar = Math.max(0.02, ruido * 3);
          if (rms > limiar) {
            falou = true;
            ultimoSom = agora;
          }
          if (
            (falou && agora - ultimoSom > silencioMs) ||
            agora - inicio > maxMs ||
            (!falou && agora - inicio > esperaMaxMs)
          ) {
            finalizar();
          }
        }, INTERVALO_MS);

        gravador.start(250);
        setGravando(true);
      });
    },
    [garantirPermissao]
  );

  // Para a gravação atual (ex.: botão "Terminei de falar")
  const parar = useCallback(() => pararRef.current?.(), []);

  return { gravarFala, parar, garantirPermissao, nivel, gravando };
}
