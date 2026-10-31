import { useCallback, useRef, useState } from "react";
import { criarSessaoRealtime } from "./api.js";

// Modo tempo real: o navegador conecta direto na OpenAI Realtime API por WebRTC.
// O áudio do microfone vai em streaming para o modelo e a voz dele volta em streaming,
// sem esperar transcrever / gerar texto / gerar MP3 (resposta em menos de 1 segundo).
// O backend só gera uma chave temporária (o token de verdade não vem para o navegador).

export function useRealtime() {
  const pcRef = useRef(null);
  const canalRef = useRef(null);
  const micRef = useRef(null);
  const audioRef = useRef(null);
  const callbacksRef = useRef({});
  const sessaoRef = useRef(null);
  const [status, setStatus] = useState("parado");

  const enviar = useCallback((evento) => {
    if (canalRef.current?.readyState === "open") canalRef.current.send(JSON.stringify(evento));
  }, []);

  const tratarEvento = useCallback(
    (ev) => {
      const cb = callbacksRef.current;
      switch (ev.type) {
        case "input_audio_buffer.speech_started":
          setStatus("ouvindo");
          break;
        case "input_audio_buffer.speech_stopped":
          setStatus("pensando");
          break;
        case "output_audio_buffer.started":
          setStatus("falando");
          break;
        case "output_audio_buffer.stopped":
        case "output_audio_buffer.cleared":
          setStatus(micRef.current?.enabled ? "ouvindo" : "parado");
          cb.aoTerminarDeFalar?.();
          break;
        case "conversation.item.input_audio_transcription.completed":
          if (ev.transcript?.trim()) cb.aoFalaUsuario?.(ev.transcript.trim());
          break;
        case "response.output_audio_transcript.done":
        case "response.audio_transcript.done":
          if (ev.transcript?.trim()) cb.aoFalaAssistente?.(ev.transcript.trim());
          break;
        case "response.done":
          for (const item of ev.response?.output ?? []) {
            if (item.type === "function_call" && item.name === "registrar_sintomas") {
              let args = {};
              try {
                args = JSON.parse(item.arguments || "{}");
              } catch {
                /* argumentos inválidos -> lista vazia */
              }
              cb.aoRegistrarSintomas?.(args.sintomas ?? [], item.call_id);
            }
          }
          break;
        case "error":
          console.error("Realtime:", ev.error);
          cb.aoErro?.(ev.error?.message ?? "Erro na sessão de voz");
          break;
        default:
      }
    },
    []
  );

  const conectar = useCallback(
    async (callbacks, perfil) => {
      callbacksRef.current = callbacks;

      const sessao = await criarSessaoRealtime(perfil);
      sessaoRef.current = sessao;

      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      // voz da assistente
      const audio = new Audio();
      audio.autoplay = true;
      audioRef.current = audio;
      pc.ontrack = (e) => (audio.srcObject = e.streams[0]);

      // microfone
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      micRef.current = stream.getAudioTracks()[0];
      pc.addTrack(micRef.current, stream);

      // canal de eventos (texto/JSON)
      const canal = pc.createDataChannel("oai-events");
      canalRef.current = canal;
      canal.onmessage = (e) => tratarEvento(JSON.parse(e.data));
      const aberto = new Promise((resolve) => (canal.onopen = resolve));

      const oferta = await pc.createOffer();
      await pc.setLocalDescription(oferta);
      const resp = await fetch("https://api.openai.com/v1/realtime/calls", {
        method: "POST",
        body: oferta.sdp,
        headers: { Authorization: `Bearer ${sessao.chave}`, "Content-Type": "application/sdp" },
      });
      if (!resp.ok) throw new Error(`Realtime API: ${resp.status} ${await resp.text()}`);
      await pc.setRemoteDescription({ type: "answer", sdp: await resp.text() });
      await aberto;

      setStatus("pensando");
      enviar({ type: "response.create" }); // a assistente começa cumprimentando
    },
    [enviar, tratarEvento]
  );

  // Liga/desliga o microfone e a detecção de fala (desligado durante a medição da pressão)
  const microfone = useCallback(
    (ligado) => {
      if (micRef.current) micRef.current.enabled = ligado;
      enviar({ type: "input_audio_buffer.clear" });
      if (!ligado) setStatus("parado");
    },
    [enviar]
  );

  // Devolve o resultado da ferramenta registrar_sintomas e a assistente fala a transição
  const responderFerramenta = useCallback(
    (callId, saida) => {
      enviar({
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: callId, output: JSON.stringify(saida) },
      });
      enviar({ type: "response.create", response: { tool_choice: "none" } });
    },
    [enviar]
  );

  // Faz a assistente falar algo com instruções específicas (sem usar ferramentas)
  const falar = useCallback(
    (instrucoes) => {
      setStatus("pensando");
      enviar({ type: "response.create", response: { instructions: instrucoes, tool_choice: "none" } });
    },
    [enviar]
  );

  // Envia um texto digitado como se fosse fala do usuário
  const enviarTexto = useCallback(
    (texto) => {
      enviar({
        type: "conversation.item.create",
        item: { type: "message", role: "user", content: [{ type: "input_text", text: texto }] },
      });
      enviar({ type: "response.create" });
    },
    [enviar]
  );

  const desconectar = useCallback(() => {
    canalRef.current?.close();
    pcRef.current?.getSenders().forEach((s) => s.track?.stop());
    pcRef.current?.close();
    if (audioRef.current) audioRef.current.srcObject = null;
    pcRef.current = canalRef.current = micRef.current = null;
    setStatus("parado");
  }, []);

  return { conectar, desconectar, microfone, responderFerramenta, falar, enviarTexto, status, sessaoRef };
}
