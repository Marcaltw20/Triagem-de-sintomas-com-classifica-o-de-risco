import { useState } from "react";

export const VERSAO_TERMO = "1.0"; // mudar quando o texto do termo mudar

export default function TermoPrivacidade({ aoAceitar }) {
  const [recusou, setRecusou] = useState(false);

  return (
    <main className="principal">
      <section className="cartao-identificacao termo-privacidade" aria-labelledby="titulo-privacidade">
        <h2 id="titulo-privacidade">Consentimento para uso de dados (LGPD)</h2>
        <p>
          O protótipo Triagem Inteligente usa nome, CPF e data de nascimento para identificar você.
          Suas respostas, dados de saúde e sinais vitais são usados para orientar a triagem.
        </p>
        <p>
          A OpenAI processa a conversa, o áudio das respostas por voz e informações como idade, sexo e
          deficiências para conduzir a entrevista. Se a câmera estiver ativada, ela verifica se a mesma
          pessoa permanece no totem durante a triagem.
        </p>
        <p>
          Quando a gravação estiver ativada, os dados do atendimento ficam no banco do sistema.
          Procure a equipe responsável pelo totem para solicitar acesso, correção ou exclusão dos dados,
          ou para retirar seu consentimento.
        </p>
        <p><strong>Ao aceitar, você autoriza o uso desses dados para esta triagem.</strong></p>

        <div className="termo-acoes">
          <button type="button" className="botao-continuar botao-recusar" onClick={() => setRecusou(true)}>
            Recusar
          </button>
          <button type="button" className="botao-continuar" onClick={() => aoAceitar({ aceito_em: new Date().toISOString(), versao_termo: VERSAO_TERMO })}>
            Aceitar e continuar
          </button>
        </div>
        <div role="status">
          {recusou && <p>Você recusou o consentimento. Procure a equipe de atendimento para receber orientação.</p>}
        </div>
      </section>
    </main>
  );
}
