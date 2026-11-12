const formato = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function formatarTemperatura(valor) {
  if (valor === null || valor === undefined || String(valor).trim() === "") return "—";
  const numero = Number(typeof valor === "string" ? valor.replace(",", ".") : valor);
  return Number.isFinite(numero) ? formato.format(numero) : "—";
}

export function formatarTextoTemperatura(texto) {
  return texto
    .replace(/(temperatura\s*=\s*)(-?\d+(?:[.,]\d+)?)/gi,
      (_, prefixo, valor) => prefixo + formatarTemperatura(valor))
    .replace(/(-?\d+(?:[.,]\d+)?)\s*°C/g,
      (_, valor) => `${formatarTemperatura(valor)} °C`);
}
