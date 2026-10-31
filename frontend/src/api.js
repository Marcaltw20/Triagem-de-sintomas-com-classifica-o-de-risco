// Toda a comunicação do front-end com o backend Python (FastAPI) passa por este arquivo.
// Em dev, o Vite redireciona /api para localhost:8000. Documentação das rotas: ../../API.md
//
//   obterConfig()           GET  /api/config
//   transcrever(blob)       POST /api/transcrever        (modo clássico)
//   conversar(hist, perfil) POST /api/chat               (modo clássico)
//   falar(texto)            POST /api/falar + GET /api/falar/{id}  (modo clássico)
//   criarSessaoRealtime(p)  POST /api/realtime           (modo tempo real)
//   medirPressao()          POST /api/pressao
//   iniciarSpo2()           POST /api/spo2/iniciar       (relógio; no modo de teste, simula)
//   ultimaSpo2()            GET  /api/spo2/ultima
//   classificar(dados)      POST /api/classificar
//   iniciarPresenca()       POST /api/presenca/iniciar   (câmera: o primeiro rosto vira o titular)
//   estadoPresenca()        GET  /api/presenca           (presente / ausente / cancelada)
//   encerrarPresenca()      POST /api/presenca/encerrar
//   gravarCancelamento(d)   POST /api/triagens/cancelada
//
// Tela de configuração (só administradores; as funções abaixo mandam o token do login):
//   entrar(email, senha) / sair()       POST /api/login / POST /api/logout
//   obterAjustes() / salvarAjustes(m)   GET / PUT /api/ajustes
//   procurarMedidores()                 GET  /api/medidores/procurar
//   cadastrarMedidor(dados)             POST /api/medidores
//   parearMedidor(id)                   POST /api/medidores/{id}/parear
//   removerMedidor(id)                  DELETE /api/medidores/{id}
//   listarUsuarios()                    GET  /api/usuarios
//   cadastrarUsuario(dados)             POST /api/usuarios
//   definirUsuarioAtivo(id, ativo)      PATCH /api/usuarios/{id}   (bloquear / desbloquear)
//   testarCamera(indice)                GET  /api/camera/testar
//   simularPresenca(evento)             POST /api/presenca/simular  (modo de teste da câmera)
//
// Banco de dados (MySQL do XAMPP):
//   estadoBanco()                       GET  /api/banco
//   ultimasTriagens()                   GET  /api/triagens
//   gravarEncaminhamento(dados)         POST /api/triagens/encaminhamento
//   (as triagens concluídas são gravadas por classificar(), que leva o campo "registro")

async function tratar(resp) {
  if (!resp.ok) {
    let detalhe = resp.statusText;
    try {
      detalhe = (await resp.json()).detail || detalhe;
    } catch {
      /* resposta sem JSON */
    }
    const erro = new Error(detalhe);
    erro.status = resp.status;
    throw erro;
  }
  return resp;
}

async function postJson(url, corpo) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  return (await tratar(resp)).json();
}

export async function obterConfig() {
  return (await tratar(await fetch("/api/config"))).json();
}

export async function transcrever(blob) {
  const form = new FormData();
  const ext = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "mp4" : "webm";
  form.append("audio", blob, `fala.${ext}`);
  const resp = await fetch("/api/transcrever", { method: "POST", body: form });
  return (await (await tratar(resp)).json()).texto;
}

// perfil = { idade, sexo, deficiencias } da identificação (nome, CPF e nascimento não vão para a LLM)
export const conversar = (historico, perfil) => postJson("/api/chat", { historico, perfil });
export const criarSessaoRealtime = (perfil) => postJson("/api/realtime", { perfil });
export const medirPressao = () => postJson("/api/pressao");
export const classificar = (dados) => postJson("/api/classificar", dados);
export const iniciarSpo2 = () => postJson("/api/spo2/iniciar");

// Token do login da configuração. Fica só na memória (não no navegador): recarregar a página ou
// sair da tela de configuração exige entrar de novo, para o próximo paciente não achar o painel aberto.
let tokenAdmin = null;

async function enviar(metodo, url, corpo) {
  const headers = {};
  if (corpo !== undefined) headers["Content-Type"] = "application/json";
  if (tokenAdmin) headers.Authorization = `Bearer ${tokenAdmin}`;
  const resp = await fetch(url, {
    method: metodo,
    headers,
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (resp.status === 401) tokenAdmin = null; // sessão expirou ou backend reiniciou
  if (resp.status === 204) return null;
  return (await tratar(resp)).json();
}

export async function entrar(email, senha) {
  const r = await postJson("/api/login", { email, senha });
  tokenAdmin = r.token;
  return r;
}

export async function sair() {
  if (!tokenAdmin) return;
  try {
    await enviar("POST", "/api/logout");
  } finally {
    tokenAdmin = null;
  }
}

export const ultimaSpo2 = () => enviar("GET", "/api/spo2/ultima");
export const obterAjustes = () => enviar("GET", "/api/ajustes");
export const salvarAjustes = (mudancas) => enviar("PUT", "/api/ajustes", mudancas);
export const procurarMedidores = () => enviar("GET", "/api/medidores/procurar");
export const cadastrarMedidor = (dados) => enviar("POST", "/api/medidores", dados);
export const parearMedidor = (id) => enviar("POST", `/api/medidores/${id}/parear`);
export const removerMedidor = (id) => enviar("DELETE", `/api/medidores/${id}`);
export const estadoBanco = () => enviar("GET", "/api/banco");
export const listarUsuarios = () => enviar("GET", "/api/usuarios");
export const cadastrarUsuario = (dados) => enviar("POST", "/api/usuarios", dados);
export const definirUsuarioAtivo = (id, ativo) => enviar("PATCH", `/api/usuarios/${id}`, { ativo });
export const ultimasTriagens = (limite = 10) => enviar("GET", `/api/triagens?limite=${limite}`);
export const gravarEncaminhamento = (dados) => postJson("/api/triagens/encaminhamento", dados);
export const gravarCancelamento = (dados) => postJson("/api/triagens/cancelada", dados);
export const iniciarPresenca = () => postJson("/api/presenca/iniciar");
export const estadoPresenca = () => enviar("GET", "/api/presenca");
export const encerrarPresenca = () => enviar("POST", "/api/presenca/encerrar");
export const testarCamera = (indice) => enviar("GET", `/api/camera/testar?indice=${indice}`);
export const simularPresenca = (evento) => enviar("POST", "/api/presenca/simular", { evento });

// Toca a fala em streaming: o áudio começa a tocar enquanto a OpenAI ainda está gerando.
// A Promise só resolve quando terminar de falar.
let audioAtual = null;
export async function falar(texto) {
  if (!texto) return;
  const { id } = await postJson("/api/falar", { texto });
  await new Promise((resolve, reject) => {
    audioAtual = new Audio(`/api/falar/${id}`);
    audioAtual.onended = audioAtual.onpause = resolve;
    audioAtual.onerror = () => reject(new Error("Falha ao gerar a voz (veja o terminal do backend)"));
    audioAtual.play().catch(reject);
  });
  audioAtual = null;
}

export function pararFala() {
  if (audioAtual) audioAtual.pause();
}
