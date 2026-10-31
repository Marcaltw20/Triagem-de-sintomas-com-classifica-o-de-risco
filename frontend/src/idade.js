// Idade em anos a partir de DD/MM/AAAA (o CPF e a data ficam só no navegador; não vão para o backend)
export function calcularIdade(nascimento) {
  const [dia, mes, ano] = nascimento.split("/").map(Number);
  if (!dia || !mes || !ano) return null;
  const hoje = new Date();
  let idade = hoje.getFullYear() - ano;
  if (hoje.getMonth() + 1 < mes || (hoje.getMonth() + 1 === mes && hoje.getDate() < dia)) idade--;
  return idade;
}
