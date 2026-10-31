
import "./Conclusao.css";

// Resultado da triagem: a cor que a árvore de decisão escolheu (POST /api/classificar),
// os dados usados e a conversa com a assistente.

const NOMES_CORES = {
  VERMELHO: "Vermelho",
  LARANJA: "Laranja",
  AMARELO: "Amarelo",
  VERDE: "Verde",
  AZUL: "Azul",
};

const NOMES_DEFICIENCIAS = {
  fisica: "Física",
  visual: "Visual",
  auditiva: "Auditiva",
  intelectual: "Intelectual ou mental",
};

function tempoAlvo(minutos) {
  return minutos === 0 ? "Atendimento imediato" : `Atendimento em até ${minutos} minutos`;
}

export default function Conclusao({
  paciente,
  idade,
  config,
  sintomas = [],
  conversa = [],
  classificacao,
  aoOuvirDeNovo,
  aoReiniciar,
}) {
  const nome = paciente?.nome || "Paciente";
  const r = classificacao?.resultado;
  const pressao = classificacao?.pressao;
  const vitais = classificacao?.vitais;
  const nomeSintoma = (chave) => config?.nomes_sintomas?.[chave] ?? chave;
  const sintomasUsados = r?.dados?.sintomas ?? sintomas;

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

        <div className="conclusao-etapas">
          <span className="conclusao-etapa-feita">✓ Identificação</span>
          <span className="conclusao-etapa-feita">✓ Conversa</span>
          <span className="conclusao-etapa-feita">✓ Pressão</span>
          <span className="conclusao-etapa-atual">4 Conclusão</span>
        </div>
      </header>

      <main className="conclusao-conteudo">
        <span className="conclusao-subtitulo">ETAPA FINAL</span>

        <h2>Triagem concluída</h2>

        <p className="conclusao-descricao">
          Esta é a sua classificação de risco, definida pela árvore de decisão a partir da conversa e dos
          sinais vitais.
        </p>

        {r && (
          <section className={`conclusao-classificacao cor-${r.cor}`} aria-live="polite">
            <div className="conclusao-classificacao-cor">
              <span>Classificação</span>
              <strong>{NOMES_CORES[r.cor] ?? r.cor}</strong>
              <em>{r.prioridade}</em>
            </div>

            <div className="conclusao-classificacao-texto">
              <strong>{tempoAlvo(r.tempo_alvo_min)}</strong>
              <p>{r.orientacao}</p>
              <p className="conclusao-motivo">
                <span>Motivo:</span> {r.motivo}
              </p>
              {classificacao?.texto && (
                <button type="button" className="conclusao-ouvir" onClick={aoOuvirDeNovo}>
                  🔊 Ouvir explicação
                </button>
              )}
            </div>
          </section>
        )}

        {r?.atendimento_prioritario && (
          <section className="conclusao-prioridade">
            <span className="conclusao-prioridade-icone" aria-hidden="true">P</span>
            <div>
              <strong>Atendimento prioritário</strong>
              <p>
                Você tem direito a ser atendido antes, dentro da sua cor de classificação (Lei 10.048/2000):{" "}
                {r.motivos_prioridade.join(", ").toLowerCase()}.
              </p>
            </div>
          </section>
        )}

        <section className="conclusao-cartao">
          <div className="conclusao-cartao-topo">
            <div>
              <h3>Resumo do atendimento</h3>
              <p>Dados usados na classificação</p>
            </div>

            {r && (
              <span className="conclusao-status">
                Nível {r.nivel} · NEWS2 {r.news2.total}
              </span>
            )}
          </div>

          <div className="conclusao-dados">
            <div>
              <span>Nome do paciente</span>
              <strong>{nome}</strong>
            </div>

            <div>
              <span>Data de nascimento</span>
              <strong>
                {paciente?.nascimento || "Não informada"}
                {idade !== null && idade !== undefined ? ` (${idade} anos)` : ""}
              </strong>
            </div>

            <div>
              <span>Sexo</span>
              <strong>{{ F: "Feminino", M: "Masculino" }[paciente?.sexo] ?? "Não informado"}</strong>
            </div>

            <div>
              <span>Deficiência</span>
              <strong>
                {r?.dados?.perfil?.deficiencias?.length
                  ? r.dados.perfil.deficiencias.map((d) => NOMES_DEFICIENCIAS[d] ?? d).join(", ")
                  : "Nenhuma"}
              </strong>
            </div>

            <div>
              <span>Pressão arterial</span>
              <strong>{pressao ? `${pressao.pas}/${pressao.pad} mmHg` : "—"}</strong>
            </div>

            <div>
              <span>Frequência cardíaca</span>
              <strong>{pressao ? `${pressao.fc} bpm` : "—"}</strong>
            </div>

            <div>
              <span>Saturação de oxigênio</span>
              <strong>{vitais ? `${vitais.spo2}%` : "—"}</strong>
            </div>

            <div>
              <span>Temperatura</span>
              <strong>{vitais ? `${vitais.temp} °C` : "—"}</strong>
            </div>
          </div>

          <div className="conclusao-respostas">
            {r?.observacoes?.map((o) => (
              <p className="conclusao-observacoes" key={o}>
                {o}
              </p>
            ))}

            <h4>Sintomas e fatores de risco registrados</h4>

            {sintomasUsados.length === 0 ? (
              <p>Nenhum sintoma relevante foi registrado.</p>
            ) : (
              <div className="conclusao-sintomas">
                {sintomasUsados.map((s) => (
                  <span key={s}>{nomeSintoma(s)}</span>
                ))}
              </div>
            )}

            {r?.outros_achados?.length > 0 && (
              <>
                <h4>Outros pontos observados</h4>
                <ul className="conclusao-achados">
                  {r.outros_achados.map((a, i) => (
                    <li key={i}>
                      <span className={`conclusao-ponto cor-${a.cor}`} />
                      {a.motivo}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <div className="conclusao-respostas">
            <h4>Conversa com a assistente</h4>

            {conversa.length === 0 ? (
              <p>Nenhuma mensagem registrada.</p>
            ) : (
              conversa.map((item, indice) => (
                <div className="conclusao-resposta" key={indice}>
                  <span>{item.role === "user" ? "Você" : "Assistente"}</span>
                  <p>{item.content}</p>
                </div>
              ))
            )}
          </div>
        </section>

        <div className="conclusao-orientacao">
          <div className="conclusao-info-icone">i</div>

          <div>
            <strong>Orientação importante</strong>

            <p>
              Aguarde as orientações da equipe de saúde. Este protótipo acadêmico não realiza diagnóstico e não
              substitui a avaliação de um profissional de saúde.
            </p>
          </div>
        </div>

        <button type="button" className="conclusao-botao" onClick={aoReiniciar}>
          Iniciar novo atendimento →
        </button>
      </main>

      <footer className="conclusao-rodape">
        Protótipo acadêmico • Não substitui avaliação de um profissional de saúde.
      </footer>
    </div>
  );
}
