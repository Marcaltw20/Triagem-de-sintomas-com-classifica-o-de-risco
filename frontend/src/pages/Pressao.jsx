import { useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import "./Triagem.css";
import "./Pressao.css";

// Medição dos sinais vitais: pressão no Omron (POST /api/pressao) e saturação no Galaxy Watch
// (o relógio envia para o backend; aqui consultamos GET /api/spo2/ultima). As duas correm juntas.
// Se a pressão falhar, dá para tentar de novo ou digitar os valores; se o relógio não enviar,
// a saturação é digitada. Sem medidor ou sem relógio (tela de configuração), os valores são digitados.
// A temperatura ainda não tem sensor e é preenchida aqui (padrão vem dos ajustes).

const VOLTA = 2 * Math.PI * 44; // circunferência do anel do cronômetro
const INTERVALO_SPO2_MS = 2000;

export default function Pressao({
  config,
  sintomas,
  tempoReal,
  dizer,
  classificando,
  erro,
  aoMedir,
}) {
  const total = config?.tempo_pressao_s ?? 120;
  const semMedidor = config?.usar_medidor === false;
  const comRelogio = config?.usar_relogio !== false;
  const [restante, setRestante] = useState(total);
  const [leitura, setLeitura] = useState(null);
  const [erroLeitura, setErroLeitura] = useState("");
  const [medindo, setMedindo] = useState(false);
  const [manual, setManual] = useState({ pas: "", pad: "", fc: "" });
  const [vitais, setVitais] = useState({ spo2: config?.spo2 ?? 98, temp: config?.temp ?? 36.5 });
  // "aguardando" (relógio), "recebido" (veio do relógio), "falhou" (relógio não enviou) ou "manual"
  const [spo2Estado, setSpo2Estado] = useState(comRelogio ? "aguardando" : "manual");
  const [pressaoPronta, setPressaoPronta] = useState(null);
  const vitaisRef = useRef(vitais);
  const spo2EstadoRef = useRef(spo2Estado);
  const cancelarSpo2Ref = useRef(() => {});
  const enviadoRef = useRef(false);
  const iniciouRef = useRef(false);
  vitaisRef.current = vitais;
  spo2EstadoRef.current = spo2Estado;

  useEffect(() => {
    if (iniciouRef.current) return;
    iniciouRef.current = true;
    if (!semMedidor) medir();
    if (comRelogio) esperarSpo2();
    return () => cancelarSpo2Ref.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cronômetro
  useEffect(() => {
    if (!medindo) return;
    const t = setInterval(() => setRestante((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(t);
  }, [medindo]);

  // De onde veio cada valor (gravado no banco): sensor ou digitado, e se era simulação (modo de teste)
  function fontes() {
    return {
      pressao_origem: pressaoPronta.origem,
      pressao_experimental: pressaoPronta.experimental,
      spo2_origem: spo2Estado === "recebido" ? "SENSOR" : "MANUAL",
      spo2_experimental: spo2Estado === "recebido" && !!config?.spo2_simulado,
    };
  }

  function enviar() {
    // pulso_irregular: o Omron avisou batimento irregular ("pulso anormal" no Manchester)
    const { pas, pad, fc, pulso_irregular } = pressaoPronta;
    aoMedir({ pas, pad, fc, pulso_irregular }, vitaisRef.current, fontes());
  }

  // Classifica quando a pressão estiver pronta e a saturação não estiver mais esperando o relógio
  useEffect(() => {
    if (!pressaoPronta || spo2Estado === "aguardando" || enviadoRef.current) return;
    enviadoRef.current = true;
    enviar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pressaoPronta, spo2Estado]);

  async function esperarSpo2() {
    cancelarSpo2Ref.current();
    let ativo = true;
    let timer;
    cancelarSpo2Ref.current = () => {
      ativo = false;
      clearTimeout(timer);
    };
    setSpo2Estado("aguardando");
    spo2EstadoRef.current = "aguardando";

    let inicio;
    try {
      inicio = (await api.iniciarSpo2()).inicio_ms;
    } catch {
      if (ativo) setSpo2Estado("falhou");
      return;
    }
    const limite = Date.now() + (config?.tempo_spo2_s ?? 90) * 1000;

    async function consultar() {
      if (!ativo) return;
      try {
        const { leitura: l } = await api.ultimaSpo2();
        if (ativo && l && l.recebido_em_ms >= inicio && spo2EstadoRef.current === "aguardando") {
          vitaisRef.current = { ...vitaisRef.current, spo2: l.spo2 };
          setVitais(vitaisRef.current);
          setSpo2Estado("recebido");
          return;
        }
      } catch {
        /* backend fora do ar por um instante: tenta de novo */
      }
      if (Date.now() > limite) {
        if (ativo && spo2EstadoRef.current === "aguardando") setSpo2Estado("falhou");
        return;
      }
      timer = setTimeout(consultar, INTERVALO_SPO2_MS);
    }
    consultar();
  }

  function digitarSpo2() {
    cancelarSpo2Ref.current();
    setSpo2Estado("manual");
  }

  async function medir() {
    setErroLeitura("");
    setLeitura(null);
    setRestante(total);
    setMedindo(true);
    try {
      const l = await api.medirPressao();
      setMedindo(false);
      setLeitura(l);
      // no modo tempo real a leitura é falada junto com o resultado (uma resposta só)
      if (!tempoReal) await dizer(`Recebi sua pressão: ${l.pas} por ${l.pad}, com ${l.fc} batimentos por minuto.`);
      setPressaoPronta({
        pas: l.pas,
        pad: l.pad,
        fc: l.fc,
        pulso_irregular: !!l.batimento_irregular,
        origem: "SENSOR",
        experimental: !!l.simulado,
      });
    } catch (e) {
      setMedindo(false);
      setErroLeitura(e.message);
      dizer("Não consegui receber a medição da pressão. Você pode tentar de novo ou digitar os valores.");
    }
  }

  function usarManual(e) {
    e.preventDefault();
    const v = { pas: Number(manual.pas), pad: Number(manual.pad), fc: Number(manual.fc) };
    if (!v.pas || !v.pad || !v.fc) return;
    setErroLeitura("");
    setLeitura({ ...v, manual: true });
    setPressaoPronta({ ...v, pulso_irregular: false, origem: "MANUAL", experimental: false });
  }

  const minutos = Math.floor(restante / 60);
  const segundos = String(restante % 60).padStart(2, "0");
  const esperandoRelogio = pressaoPronta && spo2Estado === "aguardando";

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
          <span className="triagem-etapa-feita">✓ Conversa</span>
          <span className="triagem-etapa-atual">3 Pressão</span>
          <span className="triagem-etapa-pendente">4 Conclusão</span>
        </div>
      </header>

      <main className="triagem-pagina">
        <div className="triagem-topo">
          <div>
            <span className="triagem-etiqueta">MEDIÇÃO DOS SINAIS VITAIS</span>
            <h2>{comRelogio ? "Agora vamos medir sua pressão e a oxigenação" : "Agora vamos medir sua pressão"}</h2>
            <p>
              {sintomas.length === 0
                ? "Nenhum sintoma relevante foi registrado na conversa."
                : `A assistente registrou ${sintomas.length} ${sintomas.length === 1 ? "sintoma" : "sintomas"}.`}
            </p>
          </div>
        </div>

        <div className="pressao-grade">
          <section className="pressao-cartao pressao-medicao" aria-live="polite">
            {medindo && (
              <>
                <div className="pressao-anel">
                  <svg viewBox="0 0 100 100" aria-hidden="true">
                    <circle cx="50" cy="50" r="44" className="pressao-anel-fundo" />
                    <circle
                      cx="50"
                      cy="50"
                      r="44"
                      className="pressao-anel-progresso"
                      style={{ strokeDasharray: VOLTA, strokeDashoffset: VOLTA * (1 - restante / total) }}
                    />
                  </svg>
                  <span className="pressao-tempo">
                    {minutos}:{segundos}
                  </span>
                </div>

                <ol className="pressao-passos">
                  <li>Coloque a braçadeira no braço esquerdo, na altura do coração.</li>
                  <li>Fique sentado, com os pés no chão, parado e em silêncio.</li>
                  <li>Aperte o botão <strong>iniciar</strong> do medidor e aguarde.</li>
                  {comRelogio && (
                    <li>
                      Com o relógio no outro pulso, toque em <strong>Start</strong> nele e mantenha o braço parado.
                    </li>
                  )}
                </ol>
                {config?.omron_simulado && (
                  <p className="pressao-nota">Modo de teste: a pressão chega sozinha em alguns segundos.</p>
                )}
              </>
            )}

            {leitura && (
              <div className="pressao-leitura">
                <span>Pressão medida{leitura.manual ? " (digitada)" : leitura.simulado ? " (teste)" : ""}</span>
                <strong>
                  {leitura.pas}/{leitura.pad} <small>mmHg</small>
                </strong>
                <p>{leitura.fc} batimentos por minuto</p>
                {(leitura.movimento_detectado || leitura.batimento_irregular) && (
                  <p className="pressao-nota">
                    O medidor avisou:{" "}
                    {[
                      leitura.movimento_detectado && "movimento durante a medição",
                      leitura.batimento_irregular && "batimento irregular",
                    ]
                      .filter(Boolean)
                      .join(" e ")}
                    .
                  </p>
                )}
                {esperandoRelogio && <p className="pressao-classificando">Aguardando a oxigenação do relógio...</p>}
                {classificando && <p className="pressao-classificando">Calculando sua classificação...</p>}
              </div>
            )}

            {(erroLeitura || (semMedidor && !leitura)) && (
              <div className="pressao-falha">
                {erroLeitura && (
                  <>
                    <p className="triagem-aviso" role="alert">
                      {erroLeitura}
                    </p>

                    <button type="button" className="pressao-botao" onClick={medir}>
                      Tentar ler de novo
                    </button>
                  </>
                )}

                {semMedidor && (
                  <ol className="pressao-passos">
                    <li>Coloque a braçadeira no braço esquerdo, na altura do coração.</li>
                    <li>Meça a pressão e digite abaixo os valores que aparecem no visor.</li>
                  </ol>
                )}

                <form className="pressao-manual" onSubmit={usarManual}>
                  <strong>{semMedidor ? "Valores do visor do medidor" : "Ou digite os valores do visor do medidor"}</strong>
                  <div className="pressao-campos">
                    <label>
                      Sistólica
                      <input
                        id="manual-pas"
                        type="number"
                        inputMode="numeric"
                        placeholder="120"
                        value={manual.pas}
                        onChange={(e) => setManual({ ...manual, pas: e.target.value })}
                      />
                    </label>
                    <label>
                      Diastólica
                      <input
                        id="manual-pad"
                        type="number"
                        inputMode="numeric"
                        placeholder="80"
                        value={manual.pad}
                        onChange={(e) => setManual({ ...manual, pad: e.target.value })}
                      />
                    </label>
                    <label>
                      Batimentos
                      <input
                        id="manual-fc"
                        type="number"
                        inputMode="numeric"
                        placeholder="75"
                        value={manual.fc}
                        onChange={(e) => setManual({ ...manual, fc: e.target.value })}
                      />
                    </label>
                  </div>
                  <button type="submit" className="pressao-botao secundario">
                    Usar estes valores
                  </button>
                </form>
              </div>
            )}

            {erro && (
              <p className="triagem-aviso" role="alert">
                {erro}
              </p>
            )}
            {erro && pressaoPronta && !classificando && (
              <button type="button" className="pressao-botao" onClick={enviar}>
                Tentar classificar de novo
              </button>
            )}
          </section>

          <aside className="pressao-cartao pressao-vitais">
            <strong>Outros sinais vitais</strong>

            <div className={`pressao-spo2 pressao-spo2-${spo2Estado}`}>
              {spo2Estado === "aguardando" && (
                <>
                  <p>
                    <span className="pressao-pulso" aria-hidden="true" /> Aguardando a saturação do relógio...
                  </p>
                  {config?.spo2_simulado && <p>Modo de teste: chega sozinha em alguns segundos.</p>}
                  <button type="button" className="pressao-botao secundario" onClick={digitarSpo2}>
                    Digitar o valor
                  </button>
                </>
              )}
              {spo2Estado === "recebido" && <p>✓ Saturação medida no relógio{config?.spo2_simulado ? " (teste)" : ""}.</p>}
              {spo2Estado === "falhou" && (
                <>
                  <p>O relógio não enviou a medição. Confira o valor abaixo.</p>
                  <button type="button" className="pressao-botao secundario" onClick={esperarSpo2}>
                    Esperar o relógio de novo
                  </button>
                </>
              )}
              {spo2Estado === "manual" && <p>Confira a saturação abaixo.</p>}
            </div>

            <label>
              Saturação de oxigênio (%)
              <input
                id="vital-spo2"
                type="number"
                step="1"
                disabled={spo2Estado === "aguardando"}
                value={vitais.spo2}
                onChange={(e) => setVitais({ ...vitais, spo2: e.target.value })}
              />
            </label>
            <label>
              Temperatura (°C)
              <input
                id="vital-temp"
                type="number"
                step="0.1"
                value={vitais.temp}
                onChange={(e) => setVitais({ ...vitais, temp: e.target.value })}
              />
            </label>
            <p>A temperatura ainda não tem sensor. Confira antes de terminar a medição.</p>
          </aside>
        </div>
      </main>

      <footer className="triagem-rodape">
        Protótipo acadêmico • Não substitui avaliação de um profissional de saúde.
      </footer>
    </div>
  );
}
