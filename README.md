# Triagem Inteligente — TCC 2026

Totem de triagem: a pessoa se identifica, conversa com uma assistente (LLM) por voz ou por escrito,
mede a pressão no Omron HEM-7156T e a saturação de oxigênio (SpO2) no Galaxy Watch, e recebe a
classificação de risco (cores do Protocolo de Manchester), decidida por uma árvore de decisão.

Uma tela de configuração (engrenagem ⚙ na identificação) permite cadastrar e parear medidores de
pressão, trabalhar sem medidor ou sem relógio e ligar o **modo de teste**, que simula os aparelhos.

## Estrutura

| Pasta | O que é | Veio de |
|---|---|---|
| `frontend/` | Tela do totem (React + Vite) | `Tcc_front` (área de trabalho), ligado ao backend |
| `backend/` | Servidor FastAPI: LLM, medidor de pressão e chamada à árvore | `codigos/triagem_llm/backend` |
| `arvore_decisao/` | Árvore de decisão (classificação de risco) e seus 108 testes | `codigos/arvore_decisao` |
| `pressao_arterial/` | Comunicação Bluetooth com o Omron | `codigos/Pressão arterial` |
| `relogio_spo2/` | App do Galaxy Watch 6 que mede SpO2 e envia ao backend | `projeto-spo2` (área de trabalho) |
| `banco/` | Esquema do banco MySQL (`schema.sql`), feito a partir do diagrama de classes | — |
| `reidentificacao/` | Reidentificação de pessoas pela webcam (YuNet + SFace) e seus modelos | `codigos/reidentificacao_pessoas` |
| `API.md` | Rotas entre o front-end e o backend | `codigos/triagem_llm/API.md` |

O backend encontra `arvore_decisao/` e `pressao_arterial/` sozinho (`backend/config.py`), então as
pastas precisam ficar juntas, uma ao lado da outra. O antigo `server.py` do projeto-spo2 não é mais
necessário: o próprio backend recebe as medições do relógio em `POST /spo2` (mesma porta 8000).

Arquivos novos do backend: `ajustes.py` (ajustes da tela de configuração, salvos em
`backend/ajustes.json`) e `spo2.py` (recebe o SpO2 do relógio e grava em
`backend/dados/spo2_leituras.csv`).

## Fluxo do atendimento

1. **Identificação** (`frontend/src/App.jsx`): nome, data de nascimento, CPF, sexo e deficiência, com
   teclado virtual. Quem tem uma deficiência que impede usar o totem sozinho (não enxerga a tela, não
   consegue usar os dois braços, não consegue ler nem ouvir, ou precisa de ajuda para responder) é
   encaminhado direto para a enfermagem, e a sessão termina (`frontend/src/pages/Encaminhamento.jsx`).
   Para a LLM e a árvore vão apenas a idade (calculada pela data de nascimento), o sexo e as
   deficiências. Nome, CPF e data de nascimento vão só para o banco de dados (veja "Banco de dados"),
   nunca para a OpenAI. Na conversa, a LLM usa esses dados para não
   perguntar a idade e só perguntar sobre gravidez quando faz sentido. Na árvore, 65 anos ou mais viram
   o fator de risco "idoso", e deficiência, 60 anos ou mais ou gestação dão atendimento prioritário,
   sem mudar a cor.
2. **Conversa** (`frontend/src/pages/Triagem.jsx`): a assistente pergunta o que a pessoa está sentindo.
   Dá para responder falando ou escrevendo, com o teclado virtual e as respostas rápidas "Sim", "Não"
   e "Não sei". Quando a LLM tem informação suficiente, registra os sintomas.
3. **Pressão e saturação** (`frontend/src/pages/Pressao.jsx`): cronômetro enquanto a pessoa mede a
   pressão no Omron e, ao mesmo tempo, a saturação no relógio (toca em Start no Galaxy Watch). A
   classificação só começa quando as duas chegam. Se a pressão falhar, dá para tentar de novo ou
   digitar os valores; se o relógio não enviar a tempo, a saturação é digitada. A temperatura ainda
   não tem sensor e é preenchida nesta tela.
4. **Conclusão** (`frontend/src/pages/Conclusao.jsx`): cor, prioridade, tempo-alvo, motivo e
   orientação da árvore, os sinais vitais usados, os sintomas registrados e a conversa. A assistente
   também explica o resultado em voz alta.

## Requisitos

- Python 3.10 ou mais novo.
- Node.js **22.12 ou mais novo** (o Vite 8 do front-end não roda no 22.11).
- Token da OpenAI.
- Bluetooth no computador, para o Omron (ou o modo de teste, abaixo).
- Galaxy Watch 6 com o app de `relogio_spo2/` instalado, na mesma rede Wi-Fi do computador (ou o
  modo de teste). Como instalar: `relogio_spo2/README.md`.

## Configurar (uma vez)

1. Em `backend/`, copie `.env.example` para `.env` (se ainda não existir) e coloque o token em
   `OPENAI_API_KEY`.
2. Instale as dependências:

       cd backend
       pip install -r requirements.txt

       cd ../frontend
       npm install

3. Pareie o Omron uma vez, com o aparelho em modo de pareamento:

       cd pressao_arterial
       python 3_read_latest_measurement.py

   Isso grava a chave em `pressao_arterial/omron_pairing_key.json`. A chave que já existia foi copiada
   junto, então só é preciso repetir se trocar de aparelho.

## Banco de dados (XAMPP)

Cada triagem fica gravada num banco MySQL/MariaDB local, o do XAMPP. O esquema está em
`banco/schema.sql` e segue o diagrama de classes:

| Classe do diagrama | Tabela |
|---|---|
| Usuario, Atendente, Gestor | `usuario` (uma tabela, coluna `perfil`) |
| Paciente | `paciente` (o CPF não se repete: a mesma pessoa reaproveita o cadastro) |
| Triagem | `triagem` (status `CONCLUIDA` ou `ENCAMINHADA`, modo `VOZ`/`ESCRITO`, resumo e conversa) |
| SintomaRelatado / Sintoma (91) | `sintoma_relatado` / `sintoma` |
| FatorRisco (7) | `fator_risco` + `triagem_fator_risco` |
| LeituraSinaisVitais | `leitura_sinais_vitais` (uma linha da pressão e uma da saturação/temperatura; `origem` SENSOR ou MANUAL e `experimental` = modo de teste) |
| Dispositivo | `dispositivo` (os medidores da tela de configuração e o relógio) |
| ClassificacaoRisco | `classificacao_risco` |
| RegraCombinacao (27) | `regra_combinacao` |
| CorRisco | `ENUM` nas colunas de cor |

AssistenteVoz e ArvoreDecisao são serviços (código), sem tabela. Os catálogos (sintomas, fatores de
risco e regras) e os dispositivos são preenchidos sozinhos a partir de `arvore_decisao.py` e da tela
de configuração, então nunca ficam diferentes do código.

Como usar:

1. Abra o XAMPP Control Panel e clique em **Start** no MySQL (e no Apache, se quiser o phpMyAdmin).
2. Inicie o backend. Ele cria o banco `triagem_inteligente` e as tabelas na primeira vez.
3. Faça triagens normalmente: ao fim de cada uma, a triagem é gravada. Quem é encaminhado direto à
   enfermagem também é gravado (status `ENCAMINHADA`).
4. Veja os dados em `http://localhost/phpmyadmin` ou na tela de configuração, seção "Banco de dados"
   (conexão, total e últimas triagens; dá para desligar a gravação ali).

Se o MySQL estiver desligado, a triagem funciona normalmente, só não grava (o backend avisa no log e
tenta de novo a cada 30 segundos). Conexão no `backend/.env`: `DB_HOST`, `DB_PORTA`, `DB_USUARIO`,
`DB_SENHA` (vazia no XAMPP) e `DB_NOME`. O `schema.sql` também pode ser importado à mão no phpMyAdmin.

A tabela `usuario` guarda quem pode entrar na tela de configuração (perfil `ADMIN`; veja "Tela de
configuração"). As triagens ficam com `atendente_id` vazio, porque é o próprio totem que conduz.

O banco guarda dados pessoais e de saúde (nome, CPF, sintomas). Use só dados de teste ou de
voluntários que consentiram, e não exponha o MySQL na rede.

## Rodar (2 terminais)

Backend:

    cd backend
    uvicorn server:app --host 0.0.0.0 --port 8000

`--host 0.0.0.0` é necessário para o relógio conseguir enviar o SpO2 pela rede. Se o Windows
perguntar, permita o Python no firewall (rede privada).

Front-end:

    cd frontend
    npm run dev

Abra `http://localhost:5173` no Chrome ou no Edge e permita o microfone.

Com o backend rodando, `http://localhost:8000/docs` mostra e testa as rotas da API.

## Câmera: a mesma pessoa do começo ao fim

Para que ninguém continue (ou veja) a triagem de outra pessoa, a webcam do totem confere quem está
na frente dele, usando `reidentificacao/reidentificacao.py` (módulo `backend/presenca.py`):

1. Ao tocar em "Continuar atendimento", a câmera liga e o primeiro rosto que aparece (o maior, se
   houver mais de um) vira o **titular** da triagem.
2. Durante a conversa e a medição, a tela consulta a câmera a cada segundo. Se o titular sair da
   frente, aparece o aviso "Volte para a frente do totem"; quando ele volta, o aviso some.
3. Se **outra pessoa** ficar na frente do totem enquanto o titular está fora, por 3 segundos
   seguidos, a triagem é **cancelada**: a conversa para, a tela mostra "Triagem cancelada", a
   triagem fica gravada no banco com status `CANCELADA` (e o motivo) e o totem volta ao início.
4. Se o titular ficar **10 segundos sem aparecer** na frente da câmera, a triagem também é
   cancelada; enquanto ele está fora, o aviso mostra a contagem regressiva.
5. Na conclusão, a câmera desliga.

Um acompanhante que aparece ao lado do titular não cancela nada, e um rosto parecido demais com o
titular (ele mesmo voltando com outra luz, por exemplo) também não. Nenhuma imagem é gravada: as
assinaturas faciais ficam só na memória, durante a triagem. Se a câmera não abrir, a triagem segue
normalmente, sem essa conferência.

Na tela de configuração, seção **Câmera**: ligar/desligar, escolher a webcam (com "Testar câmera"),
a semelhança mínima para reconhecer o titular (0,40), quantos segundos de outra pessoa cancelam (3) e
quantos segundos sem aparecer cancelam (10; 0 = nunca). No **modo de teste**
da câmera não é preciso webcam: a pessoa fica sempre presente, e os botões "Pessoa sai", "Pessoa
volta" e "Outra pessoa entra" simulam as situações (abra o totem em outra aba e comece uma triagem).

## Tela de configuração e modo de teste

Na tela de identificação, toque na engrenagem ⚙ no canto do cabeçalho (ou abra
`http://localhost:5173/#configuracoes`).

**Acesso só de administradores.** A tela pede e-mail e senha de um usuário da tabela `usuario` do
banco com perfil `ADMIN` (atendentes e gestores não entram). Por isso o MySQL precisa estar ligado
para entrar. Para cadastrar o primeiro administrador (ou trocar a senha, ou desbloquear):

    cd banco
    python cadastrar_usuario.py

O script pergunta nome, e-mail e senha (mínimo 8 caracteres; a senha não aparece na tela e só o hash
PBKDF2 vai para o banco). Com `--perfil GESTOR` ou `--perfil ATENDENTE` cadastra outros perfis.

Depois do primeiro administrador, o resto é feito na própria tela, seção **Usuários**: cadastrar
(nome, e-mail, perfil e senha), bloquear e desbloquear. Bloquear derruba na hora a sessão de quem
estava dentro. Ninguém consegue bloquear o próprio usuário, então sempre sobra um administrador
ativo. Depois de 5 senhas erradas seguidas o usuário é bloqueado sozinho; um administrador
desbloqueia na seção Usuários (ou, se não sobrar nenhum para entrar, rode o script de novo com o
mesmo e-mail). Ao clicar em "Sair e voltar para a triagem" (ou recarregar a página) a sessão
acaba, para o próximo paciente não encontrar o painel aberto; a sessão também expira em 8 horas.

Tudo o que muda na tela é salvo na hora em `backend/ajustes.json` e vale a partir da próxima triagem:

- **Modo de teste**: "Testar sem nenhum equipamento" simula o medidor e o relógio de uma vez; também
  dá para simular só um deles. Com o modo de teste ligado, a identificação mostra o selo "Modo de teste".
- **Medidor de pressão**: ligar/desligar o uso do medidor (desligado, a pessoa digita os valores do
  visor), escolher o medidor ativo, **cadastrar um novo** (nome, modelo e endereço Bluetooth opcional;
  "Procurar aparelhos" lista os Omron por perto), **parear** (segure o botão Bluetooth do medidor até
  o "P" piscar) e remover.
- **Relógio**: ligar/desligar o uso do relógio (desligado, a saturação é digitada), o endereço que
  vai no app do relógio e a última leitura recebida, para conferir a conexão.
- **Tempos e valores padrão**: tempo da pressão, tempo esperando o relógio, saturação e temperatura
  padrão.

## Opções no `backend/.env`

Os itens marcados com * são só os valores iniciais: depois de mudar algo na tela de configuração,
vale o que está em `backend/ajustes.json` (apague esse arquivo para voltar ao `.env`).

| Variável | Para que serve |
|---|---|
| `MODO_PADRAO` | `realtime` (voz em tempo real, mais rápido) ou `classico` (grava, transcreve e responde; mais barato) |
| `OMRON_SIMULADO` * | `1` para testar sem o aparelho: a medição chega sozinha após 8 segundos |
| `SPO2_SIMULADO` * | `1` para testar sem o relógio: a saturação chega sozinha após 6 segundos |
| `TEMPO_PRESSAO_S` * | Segundos do cronômetro da pressão |
| `TEMPO_SPO2_S` * | Segundos esperando o relógio enviar a saturação |
| `SPO2_MANUAL`, `TEMP_MANUAL` * | Valores padrão de saturação e temperatura na tela da pressão |
| `DB_HOST`, `DB_PORTA`, `DB_USUARIO`, `DB_SENHA`, `DB_NOME` | Conexão com o MySQL do XAMPP (padrão: `127.0.0.1`, `3306`, `root`, sem senha, `triagem_inteligente`) |
| `SALVAR_NO_BANCO` * | `1` grava as triagens no banco; `0` não grava |
| `USAR_CAMERA`, `CAMERA_SIMULADA` * | Conferir pela câmera que é a mesma pessoa (`1`/`0`) e simular a câmera |
| `CAMERA_INDICE`, `LIMIAR_CAMERA` * | Webcam usada (`0` = primeira) e semelhança mínima para ser a mesma pessoa (`0.40`) |
| `TEMPO_TROCA_S`, `TEMPO_ABANDONO_S` * | Segundos de outra pessoa que cancelam (`3`) e sem aparecer que cancelam (`10`; `0` = nunca) |
| `MODELO_REALTIME` | Modelo de voz do modo tempo real (`gpt-realtime-mini` por padrão, o mais barato) |

Se o modo tempo real não conectar (microfone negado ou falha na OpenAI), a conversa continua
sozinha no modo clássico, por escrito.

## Sinais vitais na árvore: Protocolo de Manchester

Os sinais vitais seguem os discriminadores do Sistema Manchester, usando tudo o que os medidores
informam (pressão, batimentos e aviso de batimento irregular do Omron; saturação do relógio;
temperatura):

| Discriminador | Regra | Cor |
|---|---|---|
| Choque | PAS < 90 mmHg **com** pulso anormal | Vermelho |
| SatO2 muito baixa | SpO2 < 90% em ar ambiente | Laranja |
| Pulso anormal | FC < 60 ou > 100 bpm, ou batimento irregular avisado pelo Omron | Laranja |
| Pressão baixa | PAS < 90 mmHg sem pulso anormal | Laranja |
| Muito quente / Quente / Febrícula | ≥ 41 °C / 38,5–40,9 °C / 37,5–38,4 °C | Laranja / Amarelo / Verde |

Duas regras ficam **além** do Manchester, marcadas no código: a crise hipertensiva (≥ 180/120, das
Diretrizes Brasileiras de Hipertensão), porque o totem mede a pressão de todos, e o NEWS2 adaptado,
como complemento que só pode subir a cor. Os limites vieram de material do UNA-SUS/UFSC e de
estudos brasileiros sobre o Manchester; confira com o manual oficial vigente na instituição.
Em menores de 16 anos os limites de pulso são de adulto (lado seguro), e o resultado avisa a
enfermagem para confirmar.

## Testes

Árvore de decisão (108 casos: 80 de sintomas e sinais vitais, 18 dos limites do Manchester e 10 de
idade, sexo e deficiência):

    cd arvore_decisao
    python testes_automaticos.py

## Observações

- Não rode `pressao_arterial/4_background_reader.py` junto com o backend: só um programa pode
  conectar no Omron por vez.
- Use fone de ouvido se a assistente "se ouvir" pelo microfone.
- Protótipo acadêmico: não substitui a avaliação de um profissional de saúde.

## Rodar pelo VS Code

Abra a pasta `triagem_inteligente` no VS Code (Arquivo > Abrir Pasta) e aperte `Ctrl+Shift+B`.
A tarefa "Iniciar tudo" abre dois terminais, um com o backend e outro com o front-end. As outras
tarefas ficam em Terminal > Executar Tarefa: "Instalar dependências" e "Testar árvore de decisão".
