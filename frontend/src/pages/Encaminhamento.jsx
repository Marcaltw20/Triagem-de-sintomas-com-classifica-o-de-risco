
import { useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import "./Conclusao.css";

// Encerramento da sessão quando a pessoa não consegue usar o totem sozinha
// (por exemplo: não enxerga a tela ou não consegue usar os dois braços para medir a pressão).
// Nada é enviado à LLM nem à árvore: a pessoa vai direto para a enfermagem, com atendimento prioritário.

const SEGUNDOS_PARA_ENCERRAR = 60;

const FALA =
  "Para o seu atendimento, procure a equipe de enfermagem. Você tem direito a atendimento prioritário. " +
  "Se precisar, peça ajuda a alguém próximo para chegar até lá.";

export default function Encaminhamento({ paciente, motivos = [], aoEncerrar }) {
  const [restante, setRestante] = useState(SEGUNDOS_PARA_ENCERRAR);
  const falouRef = useRef(false);
  const primeiroNome = paciente?.nome?.split(" ")[0] || "";
  const nome = primeiroNome.charAt(0) + primeiroNome.slice(1).toLowerCase();

  // a mensagem é falada em voz alta, porque a pessoa pode não conseguir ler a tela
  useEffect(() => {
    if (falouRef.current) return;
    falouRef.current = true;
    api.falar(FALA).catch(() => {});
    return () => api.pararFala();
  }, []);

  useEffect(() => {
    if (restante <= 0) {
      aoEncerrar?.();
      return;
    }
    const t = setTimeout(() => setRestante((r) => r - 1), 1000);
    return () => clearTimeout(t);
  }, [restante, aoEncerrar]);

  return (
    <div className="conclusao-pagina">
      <header className="conclusao-cabecalho">
        <div className="conclusao-marca">
          <div className="conclusao-logo">
            <img src="/logo.png" alt="Logo Triagem Inteligente" />
          </div>

          <div>
            <h1>Triagem Inteligente</h1>
            <p>Cuidado que começa com você</p>
          </div>
        </div>
      </header>

      <main className="conclusao-conteudo" aria-live="assertive">
        <div className="encaminhamento-icone" aria-hidden="true">
          +
        </div>

        <span className="conclusao-subtitulo">ATENDIMENTO COM A ENFERMAGEM</span>

        <h2>{nome ? `${nome}, procure` : "Procure"} a equipe de enfermagem</h2>

        <p className="conclusao-descricao">
          Sua triagem será feita por um profissional, e não pelo totem. Você tem direito a atendimento
          prioritário. Se precisar, peça ajuda a alguém próximo para chegar até lá.
        </p>

        {motivos.length > 0 && (
          <section className="conclusao-cartao encaminhamento-cartao">
            <h3>Por que o totem encaminhou você</h3>
            <ul>
              {motivos.map((m) => (
                <li key={m}>A pessoa {m}.</li>
              ))}
            </ul>
          </section>
        )}

        <button type="button" className="conclusao-botao" onClick={() => api.falar(FALA).catch(() => {})}>
          🔊 Ouvir de novo
        </button>

        <button type="button" className="conclusao-botao secundario" onClick={aoEncerrar}>
          Encerrar atendimento
        </button>

        <p className="encaminhamento-tempo">O totem volta para o início em {restante} segundos.</p>
      </main>

      <footer className="conclusao-rodape">
        Protótipo acadêmico • Não substitui avaliação de um profissional de saúde.
      </footer>
    </div>
  );
}
