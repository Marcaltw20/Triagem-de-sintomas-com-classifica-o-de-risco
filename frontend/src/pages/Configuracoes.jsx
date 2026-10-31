import { useEffect, useState } from "react";
import * as api from "../api.js";
import "./Triagem.css";
import "./Configuracoes.css";
import Usuarios from "./Usuarios.jsx";
import Camera from "./Camera.jsx";

// Tela de configuração do totem (aberta pela engrenagem da identificação ou por #configuracoes).
// Só entra quem fizer login com um usuário ADMIN da tabela `usuario` do banco (POST /api/login);
// ao voltar para a triagem a sessão é encerrada, para o próximo paciente não achar o painel aberto.
// Tudo é salvo no backend (backend/ajustes.json) e passa a valer na próxima triagem:
//   - modo de teste: simula o medidor de pressão e/ou o relógio, para testar sem os aparelhos
//   - medidor de pressão: usar ou não, cadastrar, parear, escolher o ativo e remover
//   - relógio (SpO2): usar ou não, endereço para o app do relógio e última leitura recebida
//   - banco de dados (MySQL do XAMPP): conectado?, gravar ou não, últimas triagens gravadas
//   - usuários: cadastrar, bloquear e desbloquear (Usuarios.jsx)
//   - câmera: conferir que é a mesma pessoa durante a triagem (Camera.jsx)
//   - tempos de espera e valores padrão

const FORM_VAZIO = { nome: "", modelo: "omron_hem7156t", endereco: "" };
const CORES = { VERMELHO: "#d64541", LARANJA: "#e67e22", AMARELO: "#e5b400", VERDE: "#2e9d62", AZUL: "#2f7dc1" };

function Chave({ id, ligado, aoMudar, titulo, descricao, desabilitado }) {
  return (
    <label className="config-chave" htmlFor={id}>
      <span>
        <strong>{titulo}</strong>
        {descricao && <small>{descricao}</small>}
      </span>
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={ligado}
        disabled={desabilitado}
        onChange={(e) => aoMudar(e.target.checked)}
      />
    </label>
  );
}

function horario(ms) {
  return new Date(ms).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
}

function Cabecalho({ subtitulo, children }) {
  return (
    <header className="triagem-cabecalho">
      <div className="triagem-marca">
        <div className="triagem-logo">
          <img src="/logo.png" alt="Triagem Inteligente" />
        </div>
        <div>
          <h1>Triagem Inteligente</h1>
          <p>{subtitulo}</p>
        </div>
      </div>
      {children}
    </header>
  );
}

function Login({ aoEntrar, aoSair }) {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [entrando, setEntrando] = useState(false);

  async function entrar(e) {
    e.preventDefault();
    setErro("");
    setEntrando(true);
    try {
      aoEntrar(await api.entrar(email.trim(), senha));
    } catch (falha) {
      setErro(falha.message);
      setSenha("");
    } finally {
      setEntrando(false);
    }
  }

  return (
    <div className="triagem-tela">
      <Cabecalho subtitulo="Configuração do totem">
        <button type="button" className="config-voltar" onClick={aoSair}>
          ← Voltar para a triagem
        </button>
      </Cabecalho>

      <main className="triagem-pagina">
        <form className="config-cartao config-login" onSubmit={entrar}>
          <div className="config-titulo">
            <h3>Acesso restrito</h3>
            <p>Entre com um usuário administrador cadastrado no banco de dados.</p>
          </div>
          <div className="config-campos config-campos-login">
            <label>
              E-mail
              <input
                type="email"
                autoComplete="username"
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Senha
              <input
                type="password"
                autoComplete="current-password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
              />
            </label>
          </div>
          {erro && (
            <p className="triagem-aviso" role="alert">
              {erro}
            </p>
          )}
          <button type="submit" className="pressao-botao" disabled={entrando || !email || !senha}>
            {entrando ? "Entrando..." : "Entrar"}
          </button>
          <p className="config-dica">
            Sem usuário? Cadastre um administrador com <code>python banco/cadastrar_usuario.py</code>.
          </p>
        </form>
      </main>
    </div>
  );
}

export default function Configuracoes({ aoSair }) {
  const [admin, setAdmin] = useState(null);

  async function sair() {
    await api.sair().catch(() => {});
    aoSair();
  }

  if (!admin) return <Login aoEntrar={setAdmin} aoSair={aoSair} />;
  return <Painel admin={admin} aoSair={sair} aoExpirar={() => setAdmin(null)} />;
}

function Painel({ admin, aoSair, aoExpirar }) {
  const [ajustes, setAjustes] = useState(null);
  const [numeros, setNumeros] = useState(null);
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");
  const [form, setForm] = useState(FORM_VAZIO);
  const [procurando, setProcurando] = useState(false);
  const [encontrados, setEncontrados] = useState(null);
  const [pareando, setPareando] = useState(null);
  const [ultimaSpo2, setUltimaSpo2] = useState(null);
  const [banco, setBanco] = useState(null);
  const [triagens, setTriagens] = useState([]);

  function receber(a) {
    setAjustes(a);
    setNumeros({ tempo_pressao_s: a.tempo_pressao_s, tempo_spo2_s: a.tempo_spo2_s, spo2: a.spo2, temp: a.temp });
  }

  useEffect(() => {
    api
      .obterAjustes()
      .then(receber)
      .catch((e) => (e.status === 401 ? aoExpirar() : setErro(`Não consegui falar com o backend: ${e.message}`)));
    atualizarBanco();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function atualizarBanco() {
    try {
      const b = await api.estadoBanco();
      setBanco(b);
      setTriagens(b.conectado ? await api.ultimasTriagens(8) : []);
    } catch (e) {
      if (e.status === 401) aoExpirar();
      else setBanco({ conectado: false, erro: e.message });
    }
  }

  // Última leitura do relógio, atualizada sozinha (para conferir se o relógio está chegando ao backend)
  useEffect(() => {
    let ativo = true;
    const consultar = () =>
      api
        .ultimaSpo2()
        .then((r) => ativo && setUltimaSpo2(r.leitura))
        .catch(() => {});
    consultar();
    const t = setInterval(consultar, 3000);
    return () => {
      ativo = false;
      clearInterval(t);
    };
  }, []);

  async function executar(acao, mensagem) {
    setErro("");
    setAviso("");
    try {
      const r = await acao();
      if (mensagem) setAviso(mensagem);
      return r;
    } catch (e) {
      if (e.status === 401) aoExpirar(); // sessão expirou: volta para o login
      else setErro(e.message);
      return null;
    }
  }

  async function mudar(mudancas, mensagem) {
    const a = await executar(() => api.salvarAjustes(mudancas), mensagem);
    if (a) setAjustes(a);
  }

  async function salvarNumeros(e) {
    e.preventDefault();
    const mudancas = Object.fromEntries(Object.entries(numeros).map(([k, v]) => [k, Number(v)]));
    const a = await executar(() => api.salvarAjustes(mudancas), "Tempos e valores salvos.");
    if (a) receber(a);
  }

  async function procurar() {
    setProcurando(true);
    setEncontrados(null);
    const lista = await executar(() => api.procurarMedidores());
    setProcurando(false);
    if (lista) setEncontrados(lista);
  }

  async function cadastrar(e) {
    e.preventDefault();
    if (!form.nome.trim()) {
      setErro("Dê um nome para o medidor (ex.: Omron da sala 2).");
      return;
    }
    const m = await executar(
      () => api.cadastrarMedidor({ ...form, endereco: form.endereco.trim() || null }),
      "Medidor cadastrado. Agora pareie o aparelho para poder usá-lo."
    );
    if (m) {
      setForm(FORM_VAZIO);
      setEncontrados(null);
      receber(await api.obterAjustes());
    }
  }

  async function parear(id) {
    setPareando(id);
    const m = await executar(() => api.parearMedidor(id), "Medidor pareado com sucesso.");
    setPareando(null);
    if (m) receber(await api.obterAjustes());
  }

  async function remover(m) {
    if (!window.confirm(`Remover o medidor "${m.nome}"?`)) return;
    const a = await executar(() => api.removerMedidor(m.id), "Medidor removido.");
    if (a) receber(a);
  }

  const modoTeste = ajustes && ajustes.modo_teste_pressao && ajustes.modo_teste_spo2;

  return (
    <div className="triagem-tela">
      <Cabecalho subtitulo="Configuração do totem">
        <div className="config-usuario">
          <span>
            Administrador: <strong>{admin.nome}</strong>
          </span>
          <button type="button" className="config-voltar" onClick={aoSair}>
            Sair e voltar para a triagem
          </button>
        </div>
      </Cabecalho>

      <main className="triagem-pagina">
        <div className="triagem-topo">
          <div>
            <span className="triagem-etiqueta">CONFIGURAÇÃO</span>
            <h2>Equipamentos e modo de teste</h2>
            <p>As mudanças são salvas na hora e valem a partir da próxima triagem.</p>
          </div>
        </div>

        {erro && (
          <p className="triagem-aviso" role="alert">
            {erro}
          </p>
        )}
        {aviso && (
          <p className="config-aviso-ok" role="status">
            {aviso}
          </p>
        )}

        {!ajustes ? (
          !erro && <p>Carregando...</p>
        ) : (
          <>
            {/* ---------------------------------------------------------------- Modo de teste */}
            <section className={`config-cartao ${modoTeste ? "config-teste-ligado" : ""}`}>
              <div className="config-titulo">
                <h3>Modo de teste</h3>
                <p>Simula os equipamentos para testar a triagem sem o medidor de pressão e sem o relógio.</p>
              </div>

              <Chave
                id="teste-tudo"
                titulo="Testar sem nenhum equipamento"
                descricao="Liga a simulação do medidor e do relógio de uma vez."
                ligado={!!modoTeste}
                aoMudar={(v) => mudar({ modo_teste_pressao: v, modo_teste_spo2: v })}
              />
              <Chave
                id="teste-pressao"
                titulo="Simular o medidor de pressão"
                descricao="A pressão chega sozinha cerca de 8 segundos depois de começar a medição."
                ligado={ajustes.modo_teste_pressao}
                aoMudar={(v) => mudar({ modo_teste_pressao: v })}
              />
              <Chave
                id="teste-spo2"
                titulo="Simular o relógio (saturação)"
                descricao="A saturação chega sozinha cerca de 6 segundos depois de começar a medição."
                ligado={ajustes.modo_teste_spo2}
                aoMudar={(v) => mudar({ modo_teste_spo2: v })}
              />
            </section>

            {/* ---------------------------------------------------------------- Medidor de pressão */}
            <section className="config-cartao">
              <div className="config-titulo">
                <h3>Medidor de pressão</h3>
                <p>Omron com Bluetooth (BLEsmart). Sem medidor, a pessoa digita os valores do visor.</p>
              </div>

              <Chave
                id="usar-medidor"
                titulo="Usar medidor de pressão Bluetooth"
                descricao={ajustes.usar_medidor ? "A pressão é lida do aparelho ativo abaixo." : "Desligado: a pressão é digitada na tela."}
                ligado={ajustes.usar_medidor}
                aoMudar={(v) => mudar({ usar_medidor: v })}
              />

              {ajustes.usar_medidor && (
                <>
                  <div className="config-lista" role="radiogroup" aria-label="Medidor ativo">
                    {ajustes.medidores.length === 0 && (
                      <p className="config-vazio">Nenhum medidor cadastrado. Cadastre um abaixo.</p>
                    )}
                    {ajustes.medidores.map((m) => (
                      <div key={m.id} className={`config-medidor ${m.id === ajustes.medidor_ativo ? "ativo" : ""}`}>
                        <label className="config-medidor-info">
                          <input
                            type="radio"
                            name="medidor-ativo"
                            checked={m.id === ajustes.medidor_ativo}
                            onChange={() => mudar({ medidor_ativo: m.id })}
                          />
                          <span>
                            <strong>{m.nome}</strong>
                            <small>
                              {ajustes.modelos[m.modelo] ?? m.modelo} • {m.endereco ?? "qualquer Omron por perto"}
                            </small>
                          </span>
                        </label>
                        <span className={`config-selo ${m.pareado ? "ok" : "pendente"}`}>
                          {m.pareado ? "Pareado" : "Não pareado"}
                        </span>
                        <div className="config-medidor-acoes">
                          <button
                            type="button"
                            className="pressao-botao secundario"
                            disabled={pareando !== null}
                            onClick={() => parear(m.id)}
                          >
                            {pareando === m.id ? "Pareando..." : m.pareado ? "Parear de novo" : "Parear"}
                          </button>
                          <button type="button" className="config-remover" onClick={() => remover(m)}>
                            Remover
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {pareando && (
                    <p className="config-dica">
                      Segure o botão Bluetooth do medidor até o símbolo &quot;P&quot; piscar. Isso pode levar até 20
                      segundos.
                    </p>
                  )}

                  <form className="config-form" onSubmit={cadastrar}>
                    <strong>Cadastrar novo medidor</strong>
                    <div className="config-campos">
                      <label>
                        Nome
                        <input
                          value={form.nome}
                          maxLength={60}
                          placeholder="Omron da sala 2"
                          onChange={(e) => setForm({ ...form, nome: e.target.value })}
                        />
                      </label>
                      <label>
                        Modelo
                        <select value={form.modelo} onChange={(e) => setForm({ ...form, modelo: e.target.value })}>
                          {Object.entries(ajustes.modelos).map(([chave, nome]) => (
                            <option key={chave} value={chave}>
                              {nome}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Endereço Bluetooth (opcional)
                        <input
                          value={form.endereco}
                          placeholder="AA:BB:CC:DD:EE:FF"
                          onChange={(e) => setForm({ ...form, endereco: e.target.value.toUpperCase() })}
                        />
                      </label>
                    </div>
                    <p className="config-dica">
                      Sem endereço, o totem usa qualquer Omron que estiver por perto. Com mais de um aparelho na sala,
                      use &quot;Procurar aparelhos&quot; para escolher o certo.
                    </p>

                    <div className="config-botoes">
                      <button type="button" className="pressao-botao secundario" disabled={procurando} onClick={procurar}>
                        {procurando ? "Procurando (8 s)..." : "Procurar aparelhos"}
                      </button>
                      <button type="submit" className="pressao-botao">
                        Cadastrar medidor
                      </button>
                    </div>

                    {encontrados && (
                      <div className="config-encontrados">
                        {encontrados.length === 0 ? (
                          <p className="config-vazio">Nenhum Omron encontrado. Ligue o Bluetooth do medidor e tente de novo.</p>
                        ) : (
                          encontrados.map((d) => (
                            <button
                              type="button"
                              key={d.endereco}
                              className={form.endereco === d.endereco ? "selecionado" : ""}
                              onClick={() => setForm({ ...form, endereco: d.endereco, nome: form.nome || d.nome })}
                            >
                              <strong>{d.nome}</strong>
                              <small>
                                {d.endereco}
                                {d.rssi != null && ` • sinal ${d.rssi} dBm`}
                              </small>
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </form>
                </>
              )}
            </section>

            {/* ---------------------------------------------------------------- Relógio */}
            <section className="config-cartao">
              <div className="config-titulo">
                <h3>Relógio (saturação de oxigênio)</h3>
                <p>Galaxy Watch com o app da pasta relogio_spo2. Sem relógio, a saturação é digitada.</p>
              </div>

              <Chave
                id="usar-relogio"
                titulo="Usar o relógio para medir a saturação"
                ligado={ajustes.usar_relogio}
                aoMudar={(v) => mudar({ usar_relogio: v })}
              />

              {ajustes.usar_relogio && (
                <div className="config-relogio">
                  <div>
                    <span>Endereço para o app do relógio (SERVER_URL)</span>
                    <code>{ajustes.url_relogio}</code>
                    <small>
                      Em relogio_spo2/watch-spo2/.../tracking/SpO2Uploader.kt. Se o IP do computador mudar, troque e
                      reinstale o app. O backend precisa rodar com --host 0.0.0.0.
                    </small>
                  </div>
                  <div>
                    <span>Última leitura recebida</span>
                    {ultimaSpo2 ? (
                      <>
                        <strong>{ultimaSpo2.spo2}%</strong>
                        <small>
                          {horario(ultimaSpo2.recebido_em_ms)}
                          {ultimaSpo2.simulado ? " (teste)" : " (relógio)"}
                        </small>
                      </>
                    ) : (
                      <small>Nenhuma desde que o backend foi iniciado. Meça no relógio para testar a conexão.</small>
                    )}
                  </div>
                </div>
              )}
            </section>

            {/* ---------------------------------------------------------------- Câmera */}
            <Camera ajustes={ajustes} aoMudar={mudar} aoExpirar={aoExpirar} />

            {/* ---------------------------------------------------------------- Usuários */}
            <Usuarios admin={admin} aoExpirar={aoExpirar} />

            {/* ---------------------------------------------------------------- Banco de dados */}
            <section className="config-cartao">
              <div className="config-titulo">
                <h3>Banco de dados</h3>
                <p>MySQL do XAMPP. Ligue o MySQL no XAMPP Control Panel; o banco e as tabelas são criados sozinhos.</p>
              </div>

              <Chave
                id="salvar-banco"
                titulo="Salvar as triagens no banco"
                descricao="Grava paciente, sintomas, sinais vitais e classificação ao fim de cada triagem."
                ligado={ajustes.salvar_no_banco}
                aoMudar={(v) => mudar({ salvar_no_banco: v })}
              />

              <div className="config-relogio">
                <div>
                  <span>Conexão</span>
                  {!banco ? (
                    <small>Verificando...</small>
                  ) : banco.conectado ? (
                    <>
                      <strong className="config-banco-ok">Conectado</strong>
                      <small>
                        Banco {banco.banco} em {banco.servidor} • {banco.total_triagens}{" "}
                        {banco.total_triagens === 1 ? "triagem gravada" : "triagens gravadas"}
                      </small>
                    </>
                  ) : (
                    <>
                      <strong className="config-banco-erro">Desconectado</strong>
                      <small>
                        {banco.erro} — a triagem funciona, mas não grava. Confira se o MySQL está ligado no XAMPP.
                      </small>
                    </>
                  )}
                </div>
                <div>
                  <span>Ver os dados</span>
                  <small>
                    No phpMyAdmin: <code>http://localhost/phpmyadmin</code>, banco{" "}
                    <strong className="config-texto">{banco?.banco ?? "triagem_inteligente"}</strong>.
                  </small>
                  <button type="button" className="pressao-botao secundario" onClick={atualizarBanco}>
                    Atualizar
                  </button>
                </div>
              </div>

              {triagens.length > 0 && (
                <div className="config-tabela-rolagem">
                  <table className="config-tabela">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Data</th>
                        <th>Paciente</th>
                        <th>Situação</th>
                        <th>Classificação</th>
                      </tr>
                    </thead>
                    <tbody>
                      {triagens.map((t) => (
                        <tr key={t.id}>
                          <td>{t.id}</td>
                          <td>{new Date(t.data_hora_inicio).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</td>
                          <td>{t.paciente}</td>
                          <td>{t.status === "ENCAMINHADA" ? "Encaminhada" : t.status === "CONCLUIDA" ? "Concluída" : t.status}</td>
                          <td>
                            {t.cor ? (
                              <span className="config-cor" style={{ background: CORES[t.cor] }}>
                                {t.cor} {t.nivel}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* ---------------------------------------------------------------- Tempos e valores */}
            <section className="config-cartao">
              <div className="config-titulo">
                <h3>Tempos e valores padrão</h3>
              </div>
              <form className="config-form" onSubmit={salvarNumeros}>
                <div className="config-campos">
                  <label>
                    Tempo para medir a pressão (s)
                    <input
                      type="number"
                      min="20"
                      max="600"
                      value={numeros.tempo_pressao_s}
                      onChange={(e) => setNumeros({ ...numeros, tempo_pressao_s: e.target.value })}
                    />
                  </label>
                  <label>
                    Tempo esperando o relógio (s)
                    <input
                      type="number"
                      min="20"
                      max="600"
                      value={numeros.tempo_spo2_s}
                      onChange={(e) => setNumeros({ ...numeros, tempo_spo2_s: e.target.value })}
                    />
                  </label>
                  <label>
                    Saturação padrão (%)
                    <input
                      type="number"
                      min="50"
                      max="100"
                      value={numeros.spo2}
                      onChange={(e) => setNumeros({ ...numeros, spo2: e.target.value })}
                    />
                  </label>
                  <label>
                    Temperatura padrão (°C)
                    <input
                      type="number"
                      step="0.1"
                      min="30"
                      max="45"
                      value={numeros.temp}
                      onChange={(e) => setNumeros({ ...numeros, temp: e.target.value })}
                    />
                  </label>
                </div>
                <div className="config-botoes">
                  <button type="submit" className="pressao-botao">
                    Salvar tempos e valores
                  </button>
                </div>
              </form>
            </section>
          </>
        )}
      </main>

      <footer className="triagem-rodape">
        Protótipo acadêmico • Não substitui avaliação de um profissional de saúde.
      </footer>
    </div>
  );
}
