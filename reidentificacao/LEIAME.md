# Reidentificação de pessoas

Cópia de `codigos/reidentificacao_pessoas`. O script `reidentificacao.py` continua funcionando
sozinho (abre uma janela com a webcam; `q` sai):

    python reidentificacao.py --camera 0

Na triagem, o backend importa a classe `Reidentificador` deste arquivo (em `backend/presenca.py`)
para conferir que é a mesma pessoa do começo ao fim. Os modelos YuNet e SFace ficam em `modelos/`
(baixados sozinhos se faltarem). Veja a seção "Câmera" do README principal.
