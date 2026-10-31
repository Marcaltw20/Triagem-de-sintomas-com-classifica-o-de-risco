
import { useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import { useMicrofone } from "../useMicrofone.js";
import "./Triagem.css";

// Conversa com a assistente (LLM), por voz ou por escrito.
// Dois modos, escolhidos em MODO_PADRAO no backend/.env:
//   tempo real -> voz direto com a OpenAI Realtime API (useRealtime.js); o texto digitado vai pela mesma sessão
//   clássico   -> grava -> /api/transcrever -> /api/chat -> /api/falar
// Quando a LLM registra os sintomas, a tela chama aoConcluir(sintomas, historico).

const RESPOSTAS_RAPIDAS = ["Sim", "Não", "Não sei"];

const TECLAS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
  ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
  ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ç"],
  ["Z", "X", "C", "V", "B", "N", "M"],
];

const STATUS = {
  ouvindo: "Ouvindo... pode falar",
  transcrevendo: "Entendendo o que você disse...",
  pensando: "A assistente está pensando...",
  falando: "A assistente está falando...",
  parado: "Microfone pausado",
};

export default function Triagem({
  paciente,
  perfil,
  config,
  rt,
  tempoReal,
  aoTrocarModo,
  aoConcluir,
  aoVoltar,
}) {
  const mic = useMicrofone();
  const primeiroNome = paciente?.nome?.split(" ")[0] || "paciente";
  const nomeExibicao = primeiroNome.charAt(0) + primeiroNome.slice(1).toLowerCase();

  const [mensagens, setMensagens] = useState([]);
  const [resposta, setResposta] = useState("");
  // com deficiência auditiva a conversa começa por escrito
  const surdo = perfil?.deficiencias?.includes("auditiva");
  const [modo, setModo] = useState(surdo ? "escrever" : "falar");
  const [tecladoAberto, setTecladoAberto] = useState(surdo);
  const [status, setStatus] = useState("pensando");
  const [aviso, setAviso] = useState("");

  const historicoRef = useRef([]);          // [{role, content}] enviado para /api/chat
  const tempoRealRef = useRef(tempoReal);
  const falarRef = useRef(!surdo);          // modo clássico: continuar ouvindo o microfone
  const conversandoRef = useRef(false);
  const textoPendenteRef = useRef(null);
  const concluidoRef = useRef(false);
  const iniciouRef = useRef(false);
  const fimRef = useRef(null);
  const usouVozRef = useRef(false); // alguma resposta foi falada (senão, foi tudo escrito)
  const resumoRef = useRef("");

  const statusAtual = tempoReal ? rt.status : status;
  const perguntas = mensagens.filter((m) => m.autor === "assistente").length;

  useEffect(() => {
    tempoRealRef.current = tempoReal;
  }, [tempoReal]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [mensagens]);

  function adicionar(autor, texto) {
    historicoRef.current = [
      ...historicoRef.current,
      { role: autor === "paciente" ? "user" : "assistant", content: texto },
    ];
    setMensagens((atual) => [...atual, { autor, texto }]);
  }

  function concluir(sintomas) {
    concluidoRef.current = true;
    falarRef.current = false;
    // para o banco: como a pessoa respondeu e o resumo do relato
    const relato = historicoRef.current.filter((m) => m.role === "user").map((m) => m.content);
    aoConcluir?.(sintomas, historicoRef.current, {
      modo: usouVozRef.current ? "VOZ" : relato.length ? "ESCRITO" : null,
      resumo: resumoRef.current || relato.join(" ") || null,
    });
  }

  // ------------------------------------------------------------ modo clássico
  async function dizer(texto) {
    if (tempoRealRef.current) {
      rt.falar(`Diga ao usuário, de forma natural e sem acrescentar nada: "${texto}"`);
      return;
    }
    setStatus("falando");
    try {
      await api.falar(texto);
    } catch (e) {
      setAviso(`Erro na voz: ${e.message}`);
    }
    setStatus("parado");
  }

  async function iniciarClassico() {
    const saudacao =
      `Olá, ${nomeExibicao}! Eu sou a assistente de triagem. Vou fazer algumas perguntas e ` +
      "depois medir a sua pressão. Me conte, o que você está sentindo hoje?";
    adicionar("assistente", saudacao);
    await dizer(saudacao);
    if (falarRef.current) cicloConversa();
  }

  // Ouve o usuário, manda para a LLM e fala a resposta, até a LLM registrar os sintomas
  async function cicloConversa() {
    if (conversandoRef.current || concluidoRef.current) return;
    conversandoRef.current = true;
    let silencios = 0;
    try {
      while (!concluidoRef.current) {
        let texto = textoPendenteRef.current;
        textoPendenteRef.current = null;
        if (!texto) {
          if (!falarRef.current) break;
          setStatus("ouvindo");
          const audio = await mic.gravarFala({ silencioMs: Math.max(800, config?.silencio_ms ?? 900) });
          texto = textoPendenteRef.current;
          textoPendenteRef.current = null;
          if (!texto) {
            if (!falarRef.current) break; // trocou para "Escrever" no meio da gravação
            if (!audio) {
              if (++silencios >= 2) break; // ninguém falou: pausa o microfone
              continue;
            }
            setStatus("transcrevendo");
            texto = await api.transcrever(audio);
            if (!texto) continue;
            usouVozRef.current = true;
          }
        }
        silencios = 0;
        if (await processarFala(texto)) return;
      }
      setStatus("parado");
    } catch (e) {
      setAviso(e.message);
      setStatus("parado");
    } finally {
      conversandoRef.current = false;
    }
  }

  async function processarFala(texto) {
    adicionar("paciente", texto);
    setStatus("pensando");
    const r = await api.conversar(historicoRef.current, perfil);
    if (r.resumo) resumoRef.current = r.resumo;
    adicionar("assistente", r.texto);
    if (r.sintomas_concluidos) concluidoRef.current = true;
    await dizer(r.texto);
    if (r.sintomas_concluidos) {
      concluir(r.sintomas);
      return true;
    }
    return false;
  }

  // ------------------------------------------------------------ ações da tela
  function enviarResposta(valor = resposta) {
    const texto = String(valor).trim();
    if (!texto || concluidoRef.current) return;
    setResposta("");
    setAviso("");

    if (tempoRealRef.current) {
      adicionar("paciente", texto);
      rt.enviarTexto(texto);
      return;
    }
    textoPendenteRef.current = texto;
    if (conversandoRef.current) mic.parar();
    else cicloConversa();
  }

  async function selecionarFalar() {
    setModo("falar");
    setTecladoAberto(false);
    setAviso("");
    if (tempoRealRef.current) {
      rt.microfone(true);
      return;
    }
    try {
      await mic.garantirPermissao();
    } catch {
      setAviso("Permita o acesso ao microfone para responder falando.");
      return;
    }
    falarRef.current = true;
    cicloConversa();
  }

  function selecionarEscrever() {
    setModo("escrever");
    setTecladoAberto(true);
    if (tempoRealRef.current) {
      rt.microfone(false);
      return;
    }
    falarRef.current = false;
    mic.parar();
  }

  function ouvirPergunta() {
    const ultima = [...mensagens].reverse().find((m) => m.autor === "assistente");
    if (!ultima) return;
    if (tempoRealRef.current) {
      rt.falar(`Repita para o usuário, com as mesmas palavras: "${ultima.texto}"`);
      return;
    }
    if (!conversandoRef.current) dizer(ultima.texto);
  }

  // ------------------------------------------------------------ início
  useEffect(() => {
    if (iniciouRef.current) return;
    iniciouRef.current = true;

    if (tempoRealRef.current) {
      rt.conectar({
        aoFalaUsuario: (t) => {
          usouVozRef.current = true;
          adicionar("paciente", t);
        },
        aoFalaAssistente: (t) => adicionar("assistente", t),
        aoRegistrarSintomas: (lista, callId) => {
          if (concluidoRef.current) return;
          rt.responderFerramenta(callId, {
            ok: true,
            sintomas_registrados: lista,
            proximo_passo: `Diga exatamente: "${rt.sessaoRef.current.texto_transicao}"`,
          });
          rt.microfone(false); // não escuta durante a medição da pressão
          concluir(lista);
        },
        aoErro: (m) => setAviso(m),
      }, perfil).then(() => {
        if (surdo) rt.microfone(false);
      }).catch((e) => {
        // sem a sessão de voz (microfone negado, falha na OpenAI): segue no modo clássico, por escrito
        rt.desconectar();
        tempoRealRef.current = false;
        aoTrocarModo?.(false);
        falarRef.current = false;
        setModo("escrever");
        setTecladoAberto(true);
        setAviso(
          e.name === "NotAllowedError"
            ? "Sem acesso ao microfone. Você pode responder por escrito."
            : `A conversa por voz não conectou (${e.message}). Você pode responder por escrito.`
        );
        iniciarClassico();
      });
    } else {
      iniciarClassico();
    }

    return () => {
      falarRef.current = false;
      mic.parar();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function digitar(tecla) {
    if (tecla === "APAGAR") {
      setResposta((atual) => atual.slice(0, -1));
      return;
    }
    if (tecla === "LIMPAR") {
      setResposta("");
      return;
    }
    if (tecla === "ESPAÇO") {
      setResposta((atual) => (atual + " ").slice(0, 500));
      return;
    }
    setResposta((atual) => (atual + tecla.toLowerCase()).slice(0, 500));
  }

  return (
    <div className="triagem-tela">
      <header className="triagem-cabecalho">
        <div className="triagem-marca">
          <div className="triagem-logo">
            <img src="/logo.png" alt="Triagem Inteligente" />
          </div>

          <div>
            <h1>Triagem Inteligente</h1>
            <p>Cuidado que começa com você</p>
          </div>
        </div>

        <div className="triagem-etapas">
          <span className="triagem-etapa-feita">✓ Identificação</span>
          <span className="triagem-etapa-atual">2 Conversa</span>
          <span className="triagem-etapa-pendente">3 Pressão</span>
          <span className="triagem-etapa-pendente">4 Conclusão</span>
        </div>
      </header>

      <main className="triagem-pagina">
        <div className="triagem-topo">
          <div>
            <span className="triagem-etiqueta">CONVERSA COM A ASSISTENTE</span>

            <h2>Olá, {nomeExibicao}!</h2>

            <p>
              Conte o que está sentindo. Você pode responder falando ou escrevendo.
            </p>
          </div>

          <div className="triagem-progresso" aria-live="polite">
            <div className="triagem-status">
              <span className={`triagem-status-ponto ${statusAtual}`} />
              {STATUS[statusAtual] ?? STATUS.parado}
            </div>
            <small>
              {perguntas} {perguntas === 1 ? "pergunta" : "perguntas"} · {tempoReal ? "voz em tempo real" : "modo clássico"}
            </small>
          </div>
        </div>

        <section className="triagem-chat" aria-label="Histórico da conversa">
          {mensagens.length === 0 && (
            <p className="triagem-chat-vazio">Conectando à assistente...</p>
          )}

          {mensagens.map((mensagem, i) => (
            <div
              key={i}
              className={`triagem-linha ${
                mensagem.autor === "paciente" ? "triagem-direita" : "triagem-esquerda"
              }`}
            >
              <div
                className={`triagem-balao ${
                  mensagem.autor === "paciente" ? "triagem-paciente" : "triagem-assistente"
                }`}
              >
                <strong>{mensagem.autor === "paciente" ? "Você" : "Assistente"}</strong>
                <p>{mensagem.texto}</p>
              </div>
            </div>
          ))}

          <div ref={fimRef} />
        </section>

        <section className="triagem-responder">
          <div className="triagem-responder-titulo">
            <strong>Como deseja responder?</strong>

            <button type="button" className="triagem-ouvir" onClick={ouvirPergunta}>
              🔊 Ouvir pergunta
            </button>
          </div>

          <div className="triagem-modos">
            <button
              type="button"
              className={modo === "falar" ? "selecionado" : ""}
              onClick={selecionarFalar}
            >
              🎙️ Falar
            </button>

            <button
              type="button"
              className={modo === "escrever" ? "selecionado" : ""}
              onClick={selecionarEscrever}
            >
              ⌨️ Escrever
            </button>
          </div>

          {aviso && (
            <p className="triagem-aviso" role="status">
              {aviso}
            </p>
          )}

          {modo === "falar" && (
            <div className="triagem-voz-demo">
              <span
                className={`triagem-ponto-voz ${statusAtual === "ouvindo" ? "ativo" : ""}`}
                style={{ transform: `scale(${1 + mic.nivel * 1.5})` }}
              />
              {statusAtual === "ouvindo"
                ? "Pode falar. A assistente ouve e responde em voz alta."
                : STATUS[statusAtual] ?? STATUS.parado}
              {!tempoReal && statusAtual === "ouvindo" && (
                <button type="button" className="triagem-terminei" onClick={mic.parar}>
                  Terminei de falar
                </button>
              )}
              {!tempoReal && statusAtual === "parado" && (
                <button type="button" className="triagem-terminei" onClick={selecionarFalar}>
                  Ouvir de novo
                </button>
              )}
            </div>
          )}

          <div className="triagem-opcoes">
            {RESPOSTAS_RAPIDAS.map((opcao) => (
              <button type="button" key={opcao} onClick={() => enviarResposta(opcao)}>
                {opcao}
              </button>
            ))}
          </div>

          <form
            className="triagem-formulario"
            onSubmit={(e) => {
              e.preventDefault();
              enviarResposta();
            }}
          >
            <input
              type="text"
              aria-label="Digite sua resposta"
              placeholder="Digite sua resposta aqui..."
              value={resposta}
              onChange={(e) => setResposta(e.target.value)}
              onFocus={() => {
                if (modo !== "escrever") selecionarEscrever();
              }}
              maxLength={500}
            />

            <button type="submit" className="triagem-enviar" disabled={!resposta.trim()}>
              Enviar →
            </button>
          </form>

          {modo === "escrever" && tecladoAberto && (
            <div className="triagem-teclado">
              <div className="triagem-teclado-titulo">
                <strong>Teclado virtual</strong>

                <button type="button" onClick={() => setTecladoAberto(false)}>
                  Ocultar teclado
                </button>
              </div>

              {TECLAS.map((linha, i) => (
                <div className="triagem-teclas-linha" key={i}>
                  {linha.map((tecla) => (
                    <button
                      type="button"
                      key={tecla}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => digitar(tecla)}
                    >
                      {tecla}
                    </button>
                  ))}
                </div>
              ))}

              <div className="triagem-teclas-linha">
                <button type="button" className="triagem-tecla-acao" onClick={() => digitar("LIMPAR")}>
                  Limpar
                </button>

                <button type="button" className="triagem-tecla-espaco" onClick={() => digitar("ESPAÇO")}>
                  Espaço
                </button>

                <button type="button" className="triagem-tecla-acao" onClick={() => digitar("APAGAR")}>
                  ⌫ Apagar
                </button>
              </div>
            </div>
          )}

          {modo === "escrever" && !tecladoAberto && (
            <button
              type="button"
              className="triagem-mostrar-teclado"
              onClick={() => setTecladoAberto(true)}
            >
              ⌨️ Mostrar teclado virtual
            </button>
          )}

          <div className="triagem-acoes">
            <button type="button" className="triagem-voltar" onClick={aoVoltar}>
              ← Voltar à identificação
            </button>

            <span>Quando a assistente tiver as informações, vamos medir a pressão.</span>
          </div>
        </section>
      </main>

      <footer className="triagem-rodape">
        Protótipo acadêmico • Não substitui avaliação de um profissional de saúde.
      </footer>
    </div>
  );
}
