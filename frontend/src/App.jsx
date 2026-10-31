// Fluxo do atendimento:
//   identificacao -> triagem (conversa com a LLM) -> pressao (Omron) -> conclusao (resultado da árvore)
// Da triagem até a medição, a câmera confere se é a mesma pessoa (backend/presenca.py); se outra
// pessoa ficar no lugar, a triagem é cancelada (tela "cancelada").
// Toda a comunicação com o backend passa por api.js.
import { useEffect, useRef, useState } from "react";
import "./index.css";
import * as api from "./api.js";
import { useRealtime } from "./useRealtime.js";
import { calcularIdade } from "./idade.js";
import Triagem from "./pages/Triagem";
import Pressao from "./pages/Pressao";
import Conclusao from "./pages/Conclusao";
import Encaminhamento from "./pages/Encaminhamento";
import Configuracoes from "./pages/Configuracoes";
import Cancelada from "./pages/Cancelada";

const INTERVALO_PRESENCA_MS = 1000;
const ETAPAS_VIGIADAS = ["triagem", "pressao"];


const TECLAS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
  ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
  ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
  ["Z", "X", "C", "V", "B", "N", "M"],
];

function formatarCPF(valor) {
  const numeros = valor.replace(/\D/g, "").slice(0, 11);

  return numeros
    .replace(/^(\d{3})(\d)/, "$1.$2")
    .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1-$2");
}

function formatarData(valor) {
  const numeros = valor.replace(/\D/g, "").slice(0, 8);

  if (numeros.length > 4) {
    return `${numeros.slice(0, 2)}/${numeros.slice(2, 4)}/${numeros.slice(4)}`;
  }

  if (numeros.length > 2) {
    return `${numeros.slice(0, 2)}/${numeros.slice(2)}`;
  }

  return numeros;
}

function cpfValido(cpf) {
  const numeros = cpf.replace(/\D/g, "");

  if (
    numeros.length !== 11 ||
    /^(\d)\1{10}$/.test(numeros)
  ) {
    return false;
  }

  for (let tamanho = 9; tamanho <= 10; tamanho++) {
    let soma = 0;

    for (let i = 0; i < tamanho; i++) {
      soma += Number(numeros[i]) * (tamanho + 1 - i);
    }

    const resto = (soma * 10) % 11;
    const digito = resto === 10 ? 0 : resto;

    if (digito !== Number(numeros[tamanho])) {
      return false;
    }
  }

  return true;
}

function dataValida(data) {
  const partes = data.split("/");

  if (partes.length !== 3) return false;

  const [dia, mes, ano] = partes.map(Number);
  const hoje = new Date();

  if (ano < 1900 || ano > hoje.getFullYear()) {
    return false;
  }

  const dataInformada = new Date(ano, mes - 1, dia);

  return (
    dataInformada.getFullYear() === ano &&
    dataInformada.getMonth() === mes - 1 &&
    dataInformada.getDate() === dia &&
    dataInformada <= hoje
  );
}

// Deficiências perguntadas na identificação. Se a resposta à "pergunta" for NÃO, a pessoa não
// consegue usar o totem sozinha: a sessão termina e ela é encaminhada direto para a enfermagem.
// Nos outros casos a deficiência não muda a cor da árvore, mas dá direito a atendimento prioritário.
const DEFICIENCIAS = [
  {
    chave: "fisica",
    nome: "Física",
    pergunta: "Tem os dois braços e consegue movimentá-los?",
    motivo: "não consegue usar os dois braços, e a medição da pressão precisa deles",
  },
  {
    chave: "visual",
    nome: "Visual",
    pergunta: "Consegue ler o que está escrito nesta tela?",
    motivo: "não consegue ler a tela do totem",
  },
  {
    chave: "auditiva",
    nome: "Auditiva",
    pergunta: "Consegue ler e escrever as respostas?",
    motivo: "não consegue ouvir a assistente nem ler e escrever as respostas",
  },
  {
    chave: "intelectual",
    nome: "Intelectual ou mental",
    pergunta: "Consegue responder às perguntas sozinho ou com um acompanhante aqui?",
    motivo: "precisa de ajuda para responder às perguntas da triagem",
  },
];

const ACESSIBILIDADE_VAZIA = { tem: null, tipos: [], consegue: {} };

export default function App() {
  const rt = useRealtime();
  // #configuracoes no endereço abre direto a tela de configuração
  const [etapa, setEtapa] = useState(window.location.hash === "#configuracoes" ? "configuracoes" : "identificacao");
  const [config, setConfig] = useState(null);
  const [erroConfig, setErroConfig] = useState("");
  const [tempoReal, setTempoReal] = useState(true); // modo de conversa efetivo (pode cair para o clássico)
  const [sintomas, setSintomas] = useState([]);
  const [conversa, setConversa] = useState([]);
  const [relato, setRelato] = useState({ modo: null, resumo: null }); // da conversa, para o banco
  const [classificacao, setClassificacao] = useState(null);
  const [classificando, setClassificando] = useState(false);
  const [erroClassificar, setErroClassificar] = useState("");
  const tempoRealRef = useRef(tempoReal);
  const [presenca, setPresenca] = useState(null); // { estado, mensagem, ausente_s } da câmera
  const [motivoCancelamento, setMotivoCancelamento] = useState("");
  const cancelarRef = useRef(() => {});

  useEffect(() => {
    tempoRealRef.current = tempoReal;
  }, [tempoReal]);

  function carregarConfig() {
    api
      .obterConfig()
      .then((c) => {
        setErroConfig("");
        setConfig(c);
        setTempoReal(c.modo_padrao !== "classico");
      })
      .catch(() => setErroConfig("Não consegui falar com o backend. Ele está rodando na porta 8000?"));
  }

  useEffect(carregarConfig, []);

  function abrirConfiguracoes() {
    window.location.hash = "configuracoes";
    setEtapa("configuracoes");
  }

  function sairConfiguracoes() {
    window.history.replaceState(null, "", window.location.pathname);
    carregarConfig(); // os ajustes novos valem a partir desta triagem
    setEtapa("identificacao");
  }

  useEffect(() => rt.desconectar, [rt.desconectar]);

  // Câmera: durante a conversa e a medição, consulta a cada segundo se o titular continua na frente
  useEffect(() => {
    if (!ETAPAS_VIGIADAS.includes(etapa) || !config?.usar_camera) return;
    let ativo = true;
    const t = setInterval(async () => {
      try {
        const p = await api.estadoPresenca();
        if (!ativo) return;
        if (p.estado === "cancelada") cancelarRef.current(p.mensagem);
        else setPresenca(p);
      } catch {
        /* backend fora do ar por um instante: tenta de novo */
      }
    }, INTERVALO_PRESENCA_MS);
    return () => {
      ativo = false;
      clearInterval(t);
    };
  }, [etapa, config?.usar_camera]);

  // Fala um texto fixo com a voz da assistente, no modo de conversa em uso
  async function dizer(texto) {
    if (tempoRealRef.current) {
      rt.falar(`Diga ao usuário, de forma natural e sem acrescentar nada: "${texto}"`);
      return;
    }
    try {
      await api.falar(texto);
    } catch {
      /* sem voz, o texto continua na tela */
    }
  }

  async function finalizar(pressao, vitais, fontes) {
    setClassificando(true);
    setErroClassificar("");
    try {
      // idade, sexo e deficiências vão para a árvore (65+ vira o fator de risco "idoso" lá);
      // registro vai só para o banco de dados (identificação, conversa e origem de cada medida)
      const r = await api.classificar({
        sintomas,
        perfil,
        ...pressao,
        spo2: Number(vitais.spo2),
        temp: Number(vitais.temp),
        explicar: !tempoRealRef.current,
        registro: {
          paciente: { nome: paciente.nome, cpf: paciente.cpf, data_nascimento: paciente.nascimento },
          modo_questionario: relato.modo,
          resumo: relato.resumo,
          conversa,
          ...fontes,
        },
      });
      setClassificacao({ resultado: r.resultado, texto: r.texto, pressao, vitais });
      api.encerrarPresenca().catch(() => {}); // triagem concluída: a câmera pode desligar
      setPresenca(null);
      setEtapa("conclusao");
      if (tempoRealRef.current) {
        // a própria sessão de voz explica o resultado da árvore (só os campos necessários)
        const { cor, prioridade, motivo, orientacao, atendimento_prioritario } = r.resultado;
        rt.falar(
          `${rt.sessaoRef.current.prompt_resultado}\n\nComece dizendo a pressão medida ` +
            `(${pressao.pas} por ${pressao.pad}, ${pressao.fc} batimentos por minuto).\n\n` +
            `Resultado da árvore de decisão: ${JSON.stringify({ cor, prioridade, motivo, orientacao, atendimento_prioritario })}`
        );
      } else if (r.texto) {
        api.falar(r.texto).catch(() => {});
      }
    } catch (e) {
      setErroClassificar(`Não consegui classificar: ${e.message}`);
    } finally {
      setClassificando(false);
    }
  }

  function reiniciar() {
    rt.desconectar();
    api.pararFala();
    api.encerrarPresenca().catch(() => {});
    setPresenca(null);
    setMotivoCancelamento("");
    setPaciente({ nome: "", nascimento: "", cpf: "", sexo: "" });
    setAcessibilidade(ACESSIBILIDADE_VAZIA);
    setCampoAtivo("nome");
    setMensagem("");
    setSintomas([]);
    setConversa([]);
    setRelato({ modo: null, resumo: null });
    setClassificacao(null);
    setErroClassificar("");
    setTempoReal(config?.modo_padrao !== "classico");
    setEtapa("identificacao");
  }

  const [paciente, setPaciente] = useState({
    nome: "",
    nascimento: "",
    cpf: "",
    sexo: "",
  });
  const [acessibilidade, setAcessibilidade] = useState(ACESSIBILIDADE_VAZIA);

  // O que vai para o backend: só idade, sexo e deficiências (nome, CPF e nascimento ficam aqui)
  const perfil = {
    idade: calcularIdade(paciente.nascimento),
    sexo: paciente.sexo || null,
    deficiencias: acessibilidade.tem ? acessibilidade.tipos : [],
  };
  const motivosEncaminhamento = acessibilidade.tem
    ? DEFICIENCIAS.filter((d) => acessibilidade.tipos.includes(d.chave) && acessibilidade.consegue[d.chave] === false)
        .map((d) => d.motivo)
    : [];

  function escolherDeficiencia(chave) {
    setMensagem("");
    if (chave === "nenhuma") {
      setAcessibilidade({ tem: false, tipos: [], consegue: {} });
      return;
    }
    setAcessibilidade((atual) => {
      const tipos = atual.tipos.includes(chave)
        ? atual.tipos.filter((t) => t !== chave)
        : [...atual.tipos, chave];
      return { tem: tipos.length > 0 ? true : null, tipos, consegue: atual.consegue };
    });
  }

  function responderAcessibilidade(chave, valor) {
    setMensagem("");
    setAcessibilidade((atual) => ({ ...atual, consegue: { ...atual.consegue, [chave]: valor } }));
  }

  const [campoAtivo, setCampoAtivo] = useState("nome");
  const [mensagem, setMensagem] = useState("");

  function atualizarCampo(campo, valor) {
    let novoValor = valor;

    if (campo === "cpf") {
      novoValor = formatarCPF(valor);
    }

    if (campo === "nascimento") {
      novoValor = formatarData(valor);
    }

    if (campo === "nome") {
      novoValor = valor.slice(0, 100);
    }

    setPaciente((anterior) => ({
      ...anterior,
      [campo]: novoValor,
    }));

    setMensagem("");
  }

  function digitar(tecla) {
    const valorAtual = paciente[campoAtivo];

    if (tecla === "APAGAR") {
      const numeros = valorAtual.replace(/\D/g, "");

      if (campoAtivo === "cpf" || campoAtivo === "nascimento") {
        atualizarCampo(campoAtivo, numeros.slice(0, -1));
      } else {
        atualizarCampo(campoAtivo, valorAtual.slice(0, -1));
      }

      return;
    }

    if (tecla === "LIMPAR") {
      atualizarCampo(campoAtivo, "");
      return;
    }

    if (
      campoAtivo !== "nome" &&
      !/^\d$/.test(tecla)
    ) {
      return;
    }

    if (
      campoAtivo === "nome" &&
      !/^[A-Z ]$/.test(tecla)
    ) {
      return;
    }

    atualizarCampo(
      campoAtivo,
      valorAtual + tecla
    );
  }

  function continuar() {
    if (!config) {
      setMensagem(erroConfig || "Aguarde, conectando ao sistema...");
      return;
    }

    const nomeCompleto = paciente.nome.trim();

    if (nomeCompleto.split(/\s+/).length < 2) {
      setMensagem("Por favor, informe seu nome completo.");
      return;
    }

    if (!dataValida(paciente.nascimento)) {
      setMensagem("Informe uma data de nascimento válida.");
      return;
    }

    if (!cpfValido(paciente.cpf)) {
      setMensagem("Informe um CPF válido.");
      return;
    }

    if (!paciente.sexo) {
      setMensagem("Informe o sexo.");
      return;
    }

    if (acessibilidade.tem === null) {
      setMensagem("Informe se você tem alguma deficiência.");
      return;
    }

    if (acessibilidade.tipos.some((t) => acessibilidade.consegue[t] === undefined)) {
      setMensagem("Responda à pergunta sobre a deficiência marcada.");
      return;
    }

    setMensagem("");
    if (motivosEncaminhamento.length > 0) {
      // grava no banco quem foi encaminhado direto à enfermagem (sem esperar: a tela não depende disso)
      api
        .gravarEncaminhamento({
          paciente: { nome: paciente.nome, cpf: paciente.cpf, data_nascimento: paciente.nascimento },
          perfil,
          motivos: motivosEncaminhamento,
        })
        .catch(() => {});
      setEtapa("encaminhamento");
      return;
    }
    if (config.usar_camera) {
      setPresenca({ estado: "aguardando_rosto", mensagem: "", ausente_s: 0 });
      api.iniciarPresenca().catch(() => setPresenca(null)); // sem câmera a triagem segue sem vigia
    }
    setEtapa("triagem");
  }

  function voltarIdentificacao() {
    rt.desconectar();
    api.pararFala();
    api.encerrarPresenca().catch(() => {});
    setPresenca(null);
    setTempoReal(config?.modo_padrao !== "classico");
    setEtapa("identificacao");
  }

 
  // Outra pessoa ficou no lugar do titular: encerra a conversa, grava como CANCELADA e some com os dados
  function cancelarTriagem(motivo) {
    if (etapa === "cancelada") return;
    rt.desconectar();
    api.pararFala();
    api.gravarCancelamento({
      paciente: { nome: paciente.nome, cpf: paciente.cpf, data_nascimento: paciente.nascimento },
      perfil,
      motivo,
    }).catch(() => {});
    setPresenca(null);
    setMotivoCancelamento(motivo);
    setEtapa("cancelada");
  }

  // o intervalo da câmera chama sempre a versão atual (com os dados do paciente de agora)
  useEffect(() => {
    cancelarRef.current = cancelarTriagem;
  });

  // Aviso por cima da tela quando a câmera não vê quem começou a triagem
  const avisoPresenca =
    ETAPAS_VIGIADAS.includes(etapa) && presenca && ["ausente", "aguardando_rosto"].includes(presenca.estado) ? (
      <div className={`aviso-presenca ${presenca.estado}`} role="alert">
        {presenca.estado === "ausente" ? (
          <>
            <strong>Volte para a frente do totem</strong>
            {config?.tempo_abandono_s > 0 ? (
              <span>
                A câmera não está vendo você. A triagem será cancelada em{" "}
                <b className="aviso-contagem">{Math.max(0, config.tempo_abandono_s - presenca.ausente_s)} s</b>.
              </span>
            ) : (
              <span>
                A câmera não está vendo você. Se outra pessoa ficar no seu lugar, a triagem será cancelada.
              </span>
            )}
          </>
        ) : (
          <>
            <strong>Fique de frente para a câmera</strong>
            <span>O totem confere que é a mesma pessoa do começo ao fim da triagem.</span>
          </>
        )}
      </div>
    ) : null;

if (etapa === "triagem") {
    return (
      <>
        {avisoPresenca}
      <Triagem
        paciente={paciente}
        perfil={perfil}
        config={config}
        rt={rt}
        tempoReal={tempoReal}
        aoTrocarModo={setTempoReal}
        aoVoltar={voltarIdentificacao}
        aoConcluir={(lista, historico, dadosRelato) => {
          setSintomas(lista);
          setConversa(historico);
          setRelato(dadosRelato ?? { modo: null, resumo: null });
          setEtapa("pressao");
        }}
      />
      </>
    );
  }

  if (etapa === "cancelada") {
    return <Cancelada motivo={motivoCancelamento} aoEncerrar={reiniciar} />;
  }

  if (etapa === "encaminhamento") {
    return (
      <Encaminhamento
        paciente={paciente}
        motivos={motivosEncaminhamento}
        aoEncerrar={reiniciar}
      />
    );
  }

  if (etapa === "pressao") {
    return (
      <>
        {avisoPresenca}
      <Pressao
        config={config}
        sintomas={sintomas}
        tempoReal={tempoReal}
        dizer={dizer}
        classificando={classificando}
        erro={erroClassificar}
        aoMedir={finalizar}
      />
      </>
    );
  }

  if (etapa === "configuracoes") {
    return <Configuracoes aoSair={sairConfiguracoes} />;
  }

  if (etapa === "conclusao") {
    return (
      <Conclusao
        paciente={paciente}
        idade={perfil.idade}
        config={config}
        sintomas={sintomas}
        conversa={conversa}
        classificacao={classificacao}
        aoOuvirDeNovo={() => classificacao?.texto && dizer(classificacao.texto)}
        aoReiniciar={reiniciar}
      />
    );
  }

  return (
    <div className="aplicacao">
      <header className="cabecalho">
        <div className="marca">
          <div className="logo-fundo">
            <img
              src="/logo.png"
              alt="Logotipo da Triagem Inteligente"
            />
          </div>

          <div>
            <h1>Triagem Inteligente</h1>
            <p>Cuidado que começa com você</p>
          </div>
        </div>

        <div className="etapas">
          <div className="etapa ativa">
            <span>1</span>
            Identificação
          </div>

          <div className="etapa">
            <span>2</span>
            Conversa
          </div>

          <div className="etapa">
            <span>3</span>
            Pressão
          </div>

          <div className="etapa">
            <span>4</span>
            Conclusão
          </div>

          {(config?.omron_simulado || config?.spo2_simulado) && <span className="selo-teste">Modo de teste</span>}

          <button
            type="button"
            className="botao-config"
            title="Configuração do totem"
            aria-label="Configuração do totem"
            onClick={abrirConfiguracoes}
          >
            ⚙
          </button>
        </div>
      </header>

      <main className="principal">
        <div className="introducao">
          <div className="icone-boas-vindas">♡</div>

          <h2>Olá, seja bem-vindo!</h2>

          <p>
            Para começarmos, precisamos de algumas informações.
          </p>
        </div>

        <section className="cartao-identificacao">
          <div className="titulo-cartao">
            <h3>Identificação do paciente</h3>

            <p>
              Preencha os dados abaixo para continuar.
            </p>
          </div>

          <div className="formulario">
            <label htmlFor="nome">
              Nome completo
            </label>

            <input
              id="nome"
              type="text"
              value={paciente.nome}
              onFocus={() => setCampoAtivo("nome")}
              onChange={(e) =>
                atualizarCampo("nome", e.target.value)
              }
              placeholder="Digite seu nome completo"
              autoComplete="off"
              maxLength={100}
            />

            <div className="linha-campos">
              <div className="campo">
                <label htmlFor="nascimento">
                  Data de nascimento
                </label>

                <input
                  id="nascimento"
                  type="text"
                  inputMode="none"
                  value={paciente.nascimento}
                  onFocus={() =>
                    setCampoAtivo("nascimento")
                  }
                  onChange={(e) =>
                    atualizarCampo(
                      "nascimento",
                      e.target.value
                    )
                  }
                  placeholder="DD/MM/AAAA"
                  maxLength={10}
                />
              </div>

              <div className="campo">
                <label htmlFor="cpf">
                  CPF
                </label>

                <input
                  id="cpf"
                  type="text"
                  inputMode="none"
                  value={paciente.cpf}
                  onFocus={() => setCampoAtivo("cpf")}
                  onChange={(e) =>
                    atualizarCampo("cpf", e.target.value)
                  }
                  placeholder="000.000.000-00"
                  maxLength={14}
                />
              </div>
            </div>

            <div className="grupo-escolha" role="group" aria-labelledby="rotulo-sexo">
              <span className="rotulo-escolha" id="rotulo-sexo">Sexo</span>
              <div className="opcoes-escolha">
                {[
                  ["F", "Feminino"],
                  ["M", "Masculino"],
                ].map(([valor, nome]) => (
                  <button
                    type="button"
                    key={valor}
                    className={paciente.sexo === valor ? "selecionado" : ""}
                    aria-pressed={paciente.sexo === valor}
                    onClick={() => atualizarCampo("sexo", valor)}
                  >
                    {nome}
                  </button>
                ))}
              </div>
            </div>

            <div className="grupo-escolha" role="group" aria-labelledby="rotulo-deficiencia">
              <span className="rotulo-escolha" id="rotulo-deficiencia">
                Você tem alguma deficiência? <small>Pode marcar mais de uma.</small>
              </span>
              <div className="opcoes-escolha">
                <button
                  type="button"
                  className={acessibilidade.tem === false ? "selecionado" : ""}
                  aria-pressed={acessibilidade.tem === false}
                  onClick={() => escolherDeficiencia("nenhuma")}
                >
                  Não tenho
                </button>
                {DEFICIENCIAS.map((d) => (
                  <button
                    type="button"
                    key={d.chave}
                    className={acessibilidade.tipos.includes(d.chave) ? "selecionado" : ""}
                    aria-pressed={acessibilidade.tipos.includes(d.chave)}
                    onClick={() => escolherDeficiencia(d.chave)}
                  >
                    {d.nome}
                  </button>
                ))}
              </div>

              {DEFICIENCIAS.filter((d) => acessibilidade.tipos.includes(d.chave)).map((d) => (
                <div className="pergunta-acessibilidade" key={d.chave}>
                  <span>
                    <strong>{d.nome}:</strong> {d.pergunta}
                  </span>
                  <div className="opcoes-escolha">
                    {[
                      [true, "Sim"],
                      [false, "Não"],
                    ].map(([valor, nome]) => (
                      <button
                        type="button"
                        key={nome}
                        className={acessibilidade.consegue[d.chave] === valor ? "selecionado" : ""}
                        aria-pressed={acessibilidade.consegue[d.chave] === valor}
                        onClick={() => responderAcessibilidade(d.chave, valor)}
                      >
                        {nome}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {(erroConfig || (config && !config.token_configurado)) && (
            <p className="mensagem-erro" role="alert">
              {erroConfig ||
                "Token da OpenAI não configurado. Coloque OPENAI_API_KEY em backend/.env e reinicie o backend."}
            </p>
          )}

          {mensagem && (
            <p className="mensagem-erro" role="alert">
              {mensagem}
            </p>
          )}

          <button
            type="button"
            className="botao-continuar"
            onClick={continuar}
          >
            Continuar atendimento →
          </button>
        </section>

        <section className="teclado-virtual">
          <div className="teclado-topo">
            <div>
              <strong>Teclado virtual</strong>

              <p>
                Toque nas teclas para preencher os dados.
              </p>
            </div>

            <span className="campo-selecionado">
              {campoAtivo === "nome"
                ? "Nome completo"
                : campoAtivo === "nascimento"
                ? "Data de nascimento"
                : "CPF"}
            </span>
          </div>

          <div className="teclas">
            {TECLAS.map((linha, indice) => (
              <div
                className="linha-teclado"
                key={indice}
              >
                {linha.map((tecla) => (
                  <button
                    type="button"
                    key={tecla}
                    disabled={
                      campoAtivo !== "nome" &&
                      !/^\d$/.test(tecla)
                    }
                    onMouseDown={(e) =>
                      e.preventDefault()
                    }
                    onClick={() => digitar(tecla)}
                  >
                    {tecla}
                  </button>
                ))}
              </div>
            ))}

            <div className="linha-teclado">
              <button
                type="button"
                className="tecla-acao"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => digitar("LIMPAR")}
              >
                Limpar
              </button>

              <button
                type="button"
                className="tecla-espaco"
                disabled={campoAtivo !== "nome"}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => digitar(" ")}
              >
                Espaço
              </button>

              <button
                type="button"
                className="tecla-acao"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => digitar("APAGAR")}
              >
                ⌫ Apagar
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="rodape">
        Protótipo acadêmico • Não substitui avaliação
        de um profissional de saúde.
      </footer>
    </div>
  );
}
