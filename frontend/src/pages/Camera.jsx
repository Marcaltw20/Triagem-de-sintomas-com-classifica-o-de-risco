import { useEffect, useState } from "react";
import * as api from "../api.js";

// Seção "Câmera" da tela de configuração: liga/desliga a conferência de que é a mesma pessoa do
// começo ao fim da triagem (backend/presenca.py), escolhe a webcam, ajusta a sensibilidade e,
// no modo de teste, simula a pessoa saindo, voltando ou sendo trocada.

const NOMES_ESTADO = {
  aguardando_rosto: "Esperando o primeiro rosto",
  presente: "Titular na frente do totem",
  ausente: "Titular fora da frente do totem",
  cancelada: "Triagem cancelada (outra pessoa assumiu)",
  erro: "Câmera com problema",
  desligado: "Nenhuma triagem em andamento",
};

export default function Camera({ ajustes, aoMudar, aoExpirar }) {
  const [valores, setValores] = useState({
    limiar_camera: ajustes.limiar_camera,
    tempo_troca_s: ajustes.tempo_troca_s,
    tempo_abandono_s: ajustes.tempo_abandono_s,
  });
  const [teste, setTeste] = useState(null);
  const [testando, setTestando] = useState(false);
  const [presenca, setPresenca] = useState(null);
  const [erro, setErro] = useState("");

  // estado da triagem em andamento (útil para testar com o totem aberto em outra aba)
  useEffect(() => {
    let ativo = true;
    const consultar = () =>
      api
        .estadoPresenca()
        .then((p) => ativo && setPresenca(p))
        .catch(() => {});
    consultar();
    const t = setInterval(consultar, 2000);
    return () => {
      ativo = false;
      clearInterval(t);
    };
  }, []);

  async function chamar(acao) {
    setErro("");
    try {
      return await acao();
    } catch (e) {
      if (e.status === 401) aoExpirar();
      else setErro(e.message);
      return null;
    }
  }

  async function testar() {
    setTestando(true);
    setTeste(null);
    const r = await chamar(() => api.testarCamera(ajustes.camera_indice));
    setTestando(false);
    if (r) setTeste(r);
  }

  async function simular(evento) {
    const p = await chamar(() => api.simularPresenca(evento));
    if (p) setPresenca(p);
  }

  function salvar(e) {
    e.preventDefault();
    aoMudar({
      limiar_camera: Number(valores.limiar_camera),
      tempo_troca_s: Number(valores.tempo_troca_s),
      tempo_abandono_s: Number(valores.tempo_abandono_s),
    }, "Ajustes da câmera salvos.");
  }

  return (
    <section className="config-cartao">
      <div className="config-titulo">
        <h3>Câmera (mesma pessoa na triagem)</h3>
        <p>
          O primeiro rosto que aparece vira o titular da triagem. Se outra pessoa ficar no lugar dele, a triagem é
          cancelada. Nenhuma imagem é gravada.
        </p>
      </div>

      <label className="config-chave" htmlFor="usar-camera">
        <span>
          <strong>Conferir pela câmera que é a mesma pessoa</strong>
          <small>Desligado, a triagem não usa a câmera.</small>
        </span>
        <input
          id="usar-camera"
          type="checkbox"
          role="switch"
          checked={ajustes.usar_camera}
          onChange={(e) => aoMudar({ usar_camera: e.target.checked })}
        />
      </label>

      {ajustes.usar_camera && (
        <>
          <label className="config-chave" htmlFor="teste-camera">
            <span>
              <strong>Simular a câmera (modo de teste)</strong>
              <small>Sem webcam: a pessoa fica sempre presente, e os botões abaixo simulam saída e troca.</small>
            </span>
            <input
              id="teste-camera"
              type="checkbox"
              role="switch"
              checked={ajustes.modo_teste_camera}
              onChange={(e) => aoMudar({ modo_teste_camera: e.target.checked })}
            />
          </label>

          <div className="config-relogio">
            <div>
              <span>Webcam</span>
              <select
                className="config-select"
                value={ajustes.camera_indice}
                disabled={ajustes.modo_teste_camera}
                onChange={(e) => {
                  setTeste(null);
                  aoMudar({ camera_indice: Number(e.target.value) });
                }}
              >
                {[0, 1, 2, 3].map((i) => (
                  <option key={i} value={i}>
                    Câmera {i}
                    {i === 0 ? " (padrão)" : ""}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="pressao-botao secundario"
                disabled={testando || ajustes.modo_teste_camera}
                onClick={testar}
              >
                {testando ? "Testando..." : "Testar câmera"}
              </button>
              {teste && (
                <small className={teste.ok ? "config-banco-ok" : "config-banco-erro"}>
                  {teste.mensagem}
                  {teste.ok && ` Rostos vistos agora: ${teste.rostos}.`}
                </small>
              )}
            </div>
            <div>
              <span>Triagem em andamento</span>
              <strong className="config-texto">{NOMES_ESTADO[presenca?.estado] ?? "—"}</strong>
              {presenca?.estado === "ausente" && <small>Fora há {presenca.ausente_s} s.</small>}
              {presenca?.estado === "erro" && <small>{presenca.mensagem}</small>}
              {ajustes.modo_teste_camera && (
                <div className="config-botoes-simular">
                  <button type="button" className="pressao-botao secundario" onClick={() => simular("sair")}>
                    Pessoa sai
                  </button>
                  <button type="button" className="pressao-botao secundario" onClick={() => simular("voltar")}>
                    Pessoa volta
                  </button>
                  <button type="button" className="config-remover" onClick={() => simular("trocar")}>
                    Outra pessoa entra
                  </button>
                </div>
              )}
              {ajustes.modo_teste_camera && (
                <small>Abra o totem em outra aba, comece uma triagem e use os botões.</small>
              )}
            </div>
          </div>

          {erro && (
            <p className="triagem-aviso" role="alert">
              {erro}
            </p>
          )}

          <form className="config-form" onSubmit={salvar}>
            <div className="config-campos">
              <label>
                Semelhança mínima (0,30 a 0,80)
                <input
                  type="number"
                  step="0.05"
                  min="0.3"
                  max="0.8"
                  value={valores.limiar_camera}
                  onChange={(e) => setValores({ ...valores, limiar_camera: e.target.value })}
                />
              </label>
              <label>
                Outra pessoa por quantos segundos cancela
                <input
                  type="number"
                  step="0.5"
                  min="1"
                  max="30"
                  value={valores.tempo_troca_s}
                  onChange={(e) => setValores({ ...valores, tempo_troca_s: e.target.value })}
                />
              </label>
              <label>
                Sem aparecer por quantos segundos cancela (0 = nunca)
                <input
                  type="number"
                  min="0"
                  max="900"
                  value={valores.tempo_abandono_s}
                  onChange={(e) => setValores({ ...valores, tempo_abandono_s: e.target.value })}
                />
              </label>
            </div>
            <p className="config-dica">
              Semelhança maior = mais rigoroso para reconhecer o titular quando ele volta. O padrão (0,40) funciona
              bem com boa luz; abaixe um pouco se o titular estiver sendo confundido com outra pessoa.
            </p>
            <div className="config-botoes">
              <button type="submit" className="pressao-botao">
                Salvar ajustes da câmera
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}
