import { useEffect, useState } from "react";

// Tempo da triagem: começa quando a conversa abre e para quando a árvore devolve a cor.

// Instante atual (ms), chamado nas ações da tela (início da conversa, pedido de classificação)
export function agora() {
  return Date.now();
}

// 205000 -> "3 min 25 s"; 42000 -> "42 s"
export function formatarDuracao(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  const min = Math.floor(s / 60);
  return min ? `${min} min ${String(s % 60).padStart(2, "0")} s` : `${s} s`;
}

// Relógio "m:ss" que anda a cada segundo desde `inicio` (ms); null sem início
export function useCronometro(inicio) {
  const [agora, setAgora] = useState(() => Date.now());

  useEffect(() => {
    if (!inicio) return undefined;
    const t = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(t);
  }, [inicio]);

  if (!inicio) return null;
  const s = Math.max(0, Math.floor((agora - inicio) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
