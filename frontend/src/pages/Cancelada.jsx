import { useEffect, useState } from "react";
import "./Conclusao.css";

// Triagem cancelada pela câmera: outra pessoa ficou na frente do totem no lugar de quem começou
// (backend/presenca.py). Os dados da triagem anterior somem da tela e o totem volta ao início.
// Não fala em voz alta de propósito: quem está na frente agora não é quem fez a triagem.

const SEGUNDOS_PARA_ENCERRAR = 15;

export default function Cancelada({ motivo, aoEncerrar }) {
  const [restante, setRestante] = useState(SEGUNDOS_PARA_ENCERRAR);

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
          !
        </div>

        <span className="conclusao-subtitulo">TRIAGEM CANCELADA</span>

        <h2>A triagem anterior foi cancelada</h2>

        <p className="conclusao-descricao">
          {motivo || "Outra pessoa ficou na frente do totem no lugar de quem começou a triagem."} Para a
          segurança dos dados de cada paciente, cada pessoa precisa fazer a própria triagem do começo.
        </p>

        <button type="button" className="conclusao-botao" onClick={aoEncerrar}>
          Começar uma nova triagem
        </button>

        <p className="encaminhamento-tempo">O totem volta para o início em {restante} segundos.</p>
      </main>

      <footer className="conclusao-rodape">
        Protótipo acadêmico • Não substitui avaliação de um profissional de saúde.
      </footer>
    </div>
  );
}
