import { useEffect, useState } from "react";
import * as api from "../api.js";

// Seção "Usuários" da tela de configuração (só administradores chegam aqui):
// lista quem está na tabela `usuario`, cadastra novos e bloqueia/desbloqueia.
// O backend impede bloquear o próprio usuário e o último administrador ativo.

const PERFIS = {
  ADMIN: "Administrador (acessa a configuração)",
  GESTOR: "Gestor",
  ATENDENTE: "Atendente",
};
const SENHA_MINIMA = 8;
const FORM_VAZIO = { nome: "", email: "", perfil: "ATENDENTE", senha: "", confirmacao: "" };

export default function Usuarios({ admin, aoExpirar }) {
  const [usuarios, setUsuarios] = useState(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");
  const [ocupado, setOcupado] = useState(null); // id do usuário sendo alterado, ou "novo"

  async function executar(acao, mensagem) {
    setErro("");
    setAviso("");
    try {
      const r = await acao();
      if (mensagem) setAviso(mensagem);
      return r;
    } catch (e) {
      if (e.status === 401) aoExpirar();
      else setErro(e.message);
      return null;
    }
  }

  async function carregar() {
    const lista = await executar(() => api.listarUsuarios());
    if (lista) setUsuarios(lista);
  }

  useEffect(() => {
    api
      .listarUsuarios()
      .then(setUsuarios)
      .catch((e) => (e.status === 401 ? aoExpirar() : setErro(e.message)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function cadastrar(e) {
    e.preventDefault();
    setAviso("");
    if (!form.nome.trim() || !form.email.trim()) {
      setErro("Preencha o nome e o e-mail.");
      return;
    }
    if (form.senha.length < SENHA_MINIMA) {
      setErro(`A senha precisa ter pelo menos ${SENHA_MINIMA} caracteres.`);
      return;
    }
    if (form.senha !== form.confirmacao) {
      setErro("As senhas não conferem.");
      return;
    }
    setOcupado("novo");
    const dados = { nome: form.nome.trim(), email: form.email.trim().toLowerCase(), perfil: form.perfil, senha: form.senha };
    const u = await executar(
      () => api.cadastrarUsuario(dados),
      `Usuário ${form.email.trim().toLowerCase()} cadastrado.`
    );
    setOcupado(null);
    if (u) {
      setForm(FORM_VAZIO);
      carregar();
    }
  }

  async function alternar(u) {
    const bloquear = u.ativo;
    if (bloquear && !window.confirm(`Bloquear ${u.nome}? A pessoa não conseguirá mais entrar.`)) return;
    setOcupado(u.id);
    const r = await executar(
      () => api.definirUsuarioAtivo(u.id, !bloquear),
      bloquear ? `${u.nome} foi bloqueado.` : `${u.nome} foi desbloqueado.`
    );
    setOcupado(null);
    if (r) setUsuarios((lista) => lista.map((x) => (x.id === r.id ? r : x)));
  }

  return (
    <section className="config-cartao">
      <div className="config-titulo">
        <h3>Usuários</h3>
        <p>Quem tem perfil Administrador entra nesta tela. Bloqueados não conseguem entrar.</p>
      </div>


      {usuarios === null ? (
        !erro && <p className="config-vazio">Carregando...</p>
      ) : (
        <div className="config-tabela-rolagem">
          <table className="config-tabela">
            <thead>
              <tr>
                <th>Nome</th>
                <th>E-mail</th>
                <th>Perfil</th>
                <th>Situação</th>
                <th aria-label="Ações" />
              </tr>
            </thead>
            <tbody>
              {usuarios.map((u) => {
                const euMesmo = u.email === admin.email;
                return (
                  <tr key={u.id}>
                    <td>
                      {u.nome}
                      {euMesmo && <small className="config-voce"> (você)</small>}
                    </td>
                    <td>{u.email}</td>
                    <td>{u.perfil === "ADMIN" ? "Administrador" : u.perfil === "GESTOR" ? "Gestor" : "Atendente"}</td>
                    <td>
                      <span className={`config-selo ${u.ativo ? "ok" : "bloqueado"}`}>
                        {u.ativo ? "Ativo" : "Bloqueado"}
                      </span>
                      {u.tentativas_invalidas > 0 && (
                        <small className="config-tentativas">
                          {" "}
                          {u.tentativas_invalidas} {u.tentativas_invalidas === 1 ? "senha errada" : "senhas erradas"}
                        </small>
                      )}
                    </td>
                    <td className="config-acao-usuario">
                      <button
                        type="button"
                        className={u.ativo ? "config-remover" : "pressao-botao secundario"}
                        disabled={euMesmo || ocupado !== null}
                        title={euMesmo ? "Você não pode bloquear o seu próprio usuário" : undefined}
                        onClick={() => alternar(u)}
                      >
                        {ocupado === u.id ? "..." : u.ativo ? "Bloquear" : "Desbloquear"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* mensagens abaixo da tabela: assim as linhas não mudam de lugar entre um toque e outro */}
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

      <form className="config-form" onSubmit={cadastrar} autoComplete="off">
        <strong>Cadastrar novo usuário</strong>
        <div className="config-campos">
          <label>
            Nome
            <input
              value={form.nome}
              maxLength={100}
              onChange={(e) => setForm({ ...form, nome: e.target.value })}
            />
          </label>
          <label>
            E-mail
            <input
              type="email"
              value={form.email}
              maxLength={150}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </label>
          <label>
            Perfil
            <select value={form.perfil} onChange={(e) => setForm({ ...form, perfil: e.target.value })}>
              {Object.entries(PERFIS).map(([chave, nome]) => (
                <option key={chave} value={chave}>
                  {nome}
                </option>
              ))}
            </select>
          </label>
          <label>
            Senha (mínimo {SENHA_MINIMA})
            <input
              type="password"
              autoComplete="new-password"
              value={form.senha}
              onChange={(e) => setForm({ ...form, senha: e.target.value })}
            />
          </label>
          <label>
            Repita a senha
            <input
              type="password"
              autoComplete="new-password"
              value={form.confirmacao}
              onChange={(e) => setForm({ ...form, confirmacao: e.target.value })}
            />
          </label>
        </div>
        <div className="config-botoes">
          <button type="submit" className="pressao-botao" disabled={ocupado !== null}>
            {ocupado === "novo" ? "Cadastrando..." : "Cadastrar usuário"}
          </button>
        </div>
      </form>
    </section>
  );
}
