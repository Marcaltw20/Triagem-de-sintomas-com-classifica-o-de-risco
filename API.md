# API entre o front-end e o backend

O front-end (React, porta 5173) e o backend (FastAPI, porta 8000) conversam só por estas rotas.
Em desenvolvimento, o Vite repassa tudo o que começa com `/api` para `http://localhost:8000`
(`frontend/vite.config.js`), então o front chama sempre caminhos relativos, como `/api/config`.

Onde fica cada parte:

| Lado | Arquivo | O que tem |
|---|---|---|
| Backend | `backend/api.py` | As rotas |
| Backend | `backend/schemas.py` | O formato JSON de cada requisição e resposta |
| Backend | `backend/server.py` | Só monta o servidor e registra as rotas |
| Front-end | `frontend/src/api.js` | Uma função para cada rota; nenhum outro arquivo chama o backend |

Com o backend rodando, `http://localhost:8000/docs` mostra todas as rotas e permite testá-las pelo
navegador.

## Resumo

| Rota | Função no front (`api.js`) | Modo | Quando é chamada |
|---|---|---|---|
| `GET /api/config` | `obterConfig()` | Os dois | Ao abrir a tela |
| `POST /api/realtime` | `criarSessaoRealtime()` | Tempo real | Ao tocar em "começar" |
| `POST /api/transcrever` | `transcrever(blob)` | Clássico | Cada vez que o usuário termina de falar |
| `POST /api/chat` | `conversar(historico)` | Clássico | Depois de cada transcrição |
| `POST /api/falar` | `falar(texto)` | Clássico | Cada vez que a assistente vai falar |
| `GET /api/falar/{id}` | `falar(texto)` | Clássico | Logo depois do `POST /api/falar` |
| `POST /api/pressao` | `medirPressao()` | Os dois | Depois que os sintomas são registrados |
| `POST /api/spo2/iniciar` | `iniciarSpo2()` | Os dois | Junto com a medição da pressão |
| `GET /api/spo2/ultima` | `ultimaSpo2()` | Os dois | A cada 2 s, até chegar a saturação do relógio |
| `POST /api/classificar` | `classificar(dados)` | Os dois | Depois da pressão e da saturação |
| `GET`/`PUT /api/ajustes` | `obterAjustes()` / `salvarAjustes()` | — | Tela de configuração |
| `GET /api/medidores/procurar` | `procurarMedidores()` | — | Tela de configuração |
| `POST /api/medidores` | `cadastrarMedidor()` | — | Tela de configuração |
| `POST /api/medidores/{id}/parear` | `parearMedidor(id)` | — | Tela de configuração |
| `DELETE /api/medidores/{id}` | `removerMedidor(id)` | — | Tela de configuração |
| `POST /spo2` | — (app do relógio) | — | O Galaxy Watch envia cada medição |

## A triagem passo a passo

**Modo tempo real.** O front pede a configuração e depois uma chave temporária em
`/api/realtime`. Com ela, o navegador conversa direto com a OpenAI; essa conversa não passa pelo
backend. Quando a LLM registra os sintomas, o front chama `/api/pressao`, espera a medição e
manda tudo para `/api/classificar` com `explicar: false`, porque quem explica o resultado é a
própria sessão de voz.

**Modo clássico.** Cada fala do usuário vira um ciclo de três chamadas: `/api/transcrever`
transforma o áudio em texto, `/api/chat` manda o histórico para a LLM e `/api/falar` gera a voz da
resposta. O ciclo se repete até `/api/chat` devolver `sintomas_concluidos: true`. Daí em diante é
igual ao outro modo, só que `/api/classificar` é chamada com `explicar: true` e já devolve a frase
que a assistente vai falar.

## Erros

Toda resposta de erro tem o mesmo formato:

```json
{ "detail": "Texto explicando o que deu errado" }
```

A função `tratar()` de `api.js` transforma esse texto na mensagem que aparece na tela.

| Código | Quando acontece |
|---|---|
| 404 | Fala não encontrada em `GET /api/falar/{id}` |
| 408 | Nenhuma medição chegou do Omron dentro do tempo |
| 422 | Dados inválidos: sinal vital fora da faixa, sintoma desconhecido ou JSON fora do formato |
| 500 | Falha no medidor de pressão |
| 502 | Falha na OpenAI (token errado, sem internet, limite de uso) |

## Perfil do paciente

Três rotas aceitam o campo opcional `perfil`, com dados da tela de identificação:

```json
{ "idade": 70, "sexo": "F", "deficiencias": ["visual"] }
```

| Campo | Valores |
|---|---|
| `idade` | Anos, de 0 a 130, calculados pela data de nascimento |
| `sexo` | `"F"` ou `"M"` |
| `deficiencias` | Lista com `"fisica"`, `"visual"`, `"auditiva"` e/ou `"intelectual"` |

Nome, CPF e data de nascimento não fazem parte do perfil: vão só no campo `registro` de
`/api/classificar` (e em `/api/triagens/encaminhamento`), para o banco de dados, nunca para a LLM.

- Em `/api/chat` e `/api/realtime`, o perfil adapta a conversa: a LLM não pergunta a idade, só pergunta
  sobre gravidez quando faz sentido (sexo feminino entre 10 e 55 anos, ou sexo não informado) e ajusta a
  forma de falar à deficiência informada.
- Em `/api/classificar`, o perfil entra na árvore: 65 anos ou mais viram o fator de risco "idoso", chaves
  incompatíveis com o sexo são ignoradas, e deficiência, 60 anos ou mais ou gestação dão atendimento
  prioritário, sem mudar a cor.

Quem tem uma deficiência que impede usar o totem sozinho (não enxerga a tela, não consegue usar os dois
braços, não consegue ler nem ouvir, ou precisa de ajuda para responder) é encaminhado direto para a
enfermagem na própria tela de identificação. Nesse caso nenhuma rota é chamada.

## Rotas

### GET /api/config

Devolve as configurações que a tela precisa ao abrir.

Resposta:

```json
{
  "tempo_pressao_s": 120,
  "tempo_spo2_s": 90,
  "spo2": 98,
  "temp": 36.5,
  "omron_simulado": false,
  "spo2_simulado": false,
  "usar_medidor": true,
  "usar_relogio": true,
  "medidor": "Omron do totem",
  "modo_padrao": "realtime",
  "silencio_ms": 600,
  "nomes_sintomas": { "febre": "Febre", "dor_toracica": "Dor no peito" },
  "token_configurado": true
}
```

| Campo | Significado |
|---|---|
| `tempo_pressao_s` | Duração do cronômetro da medição de pressão, em segundos |
| `tempo_spo2_s` | Quanto tempo esperar a saturação do relógio, em segundos |
| `spo2`, `temp` | Valores padrão de saturação (sem leitura do relógio) e temperatura (sem sensor) |
| `omron_simulado` | `true` no modo de teste do medidor (pressão falsa, sem o aparelho) |
| `spo2_simulado` | `true` no modo de teste do relógio (saturação falsa, sem o relógio) |
| `usar_medidor` | `false` quando não há medidor (ou nenhum cadastrado): a pressão é digitada |
| `usar_relogio` | `false` quando não há relógio: a saturação é digitada |
| `medidor` | Nome do medidor de pressão ativo |

Esses valores vêm da tela de configuração (`backend/ajustes.json`); sem ela, do `.env`.
| `modo_padrao` | `"realtime"` ou `"classico"` |
| `silencio_ms` | Quanto silêncio encerra a fala do usuário |
| `nomes_sintomas` | Nome de cada chave de sintoma, para mostrar na tela (98 chaves; o exemplo mostra duas) |
| `token_configurado` | `false` quando falta o token da OpenAI no `.env` |

### POST /api/realtime

Cria uma chave temporária para o navegador conectar direto na Realtime API da OpenAI. O token de
verdade nunca sai do backend. A chave já vem com o prompt, a ferramenta `registrar_sintomas` e a
voz configurados.

Corpo opcional: `{ "perfil": { ... } }` (veja "Perfil do paciente"). Resposta:

```json
{
  "chave": "ek_...",
  "modelo": "gpt-realtime-mini",
  "texto_transicao": "Obrigada, anotei seus sintomas. Agora vamos medir sua pressão...",
  "prompt_resultado": "Você é a assistente virtual de triagem..."
}
```

| Campo | Significado |
|---|---|
| `chave` | Chave temporária usada pelo navegador na conexão WebRTC |
| `modelo` | Modelo de voz da sessão |
| `texto_transicao` | Frase que a assistente fala ao terminar a entrevista |
| `prompt_resultado` | Instruções para a sessão explicar o resultado da árvore |

Erro possível: 502.

### POST /api/transcrever

Recebe o áudio de uma fala do usuário e devolve o texto. É um envio de arquivo
(`multipart/form-data`), não JSON.

Requisição: campo `audio` com o arquivo gravado (`webm`, `ogg` ou `mp4`).

Resposta:

```json
{ "texto": "estou com dor de cabeça desde ontem" }
```

Áudios com menos de 1 KB voltam com `texto` vazio, sem chamar a OpenAI. Erro possível: 502.

### POST /api/chat

Manda a conversa inteira para a LLM e devolve a próxima fala da assistente.

Requisição:

```json
{
  "historico": [
    { "role": "assistant", "content": "Olá! O que você está sentindo hoje?" },
    { "role": "user", "content": "Estou com febre e tosse" }
  ],
  "perfil": { "idade": 34, "sexo": "M", "deficiencias": [] }
}
```

`role` só aceita `"user"` ou `"assistant"`. `perfil` é opcional (veja "Perfil do paciente").

Resposta enquanto a entrevista continua:

```json
{ "texto": "Você está sentindo falta de ar?", "sintomas_concluidos": false, "sintomas": [], "resumo": "" }
```

Resposta quando a LLM encerra a entrevista:

```json
{
  "texto": "Obrigada, anotei seus sintomas. Agora vamos medir sua pressão...",
  "sintomas_concluidos": true,
  "sintomas": ["febre", "tosse"],
  "resumo": "Febre e tosse há dois dias, sem falta de ar."
}
```

| Campo | Significado |
|---|---|
| `texto` | O que a assistente vai falar |
| `sintomas_concluidos` | `true` quando é hora de medir a pressão |
| `sintomas` | Chaves do catálogo da árvore; só vem preenchido no fim |
| `resumo` | Uma frase com o que o usuário relatou |

Erro possível: 502.

### POST /api/falar e GET /api/falar/{id}

Transformam um texto em voz. São duas chamadas para que o áudio possa tocar em streaming: o
navegador começa a tocar antes de a OpenAI terminar de gerar.

Primeiro, `POST /api/falar` guarda o texto:

```json
{ "texto": "Você está sentindo falta de ar?" }
```

e devolve um id:

```json
{ "id": "3f2a9c..." }
```

Depois, o front toca `GET /api/falar/{id}`, que devolve o áudio MP3 (`audio/mpeg`). Cada id só pode
ser tocado uma vez.

As falas já geradas ficam guardadas em `backend/cache_voz/` e não são cobradas de novo.

Erros possíveis: 404 (id inexistente ou já usado) e 502.

### POST /api/pressao

Espera uma medição nova do Omron HEM-7156T, por até `tempo_pressao_s` + 15 segundos. Só uma
medição pode estar em andamento por vez.

Sem corpo na requisição. Resposta:

```json
{
  "pas": 128,
  "pad": 82,
  "fc": 76,
  "datahora": "2026-10-23T16:46:50",
  "movimento_detectado": false,
  "batimento_irregular": false,
  "simulado": false
}
```

| Campo | Significado |
|---|---|
| `pas`, `pad` | Pressão sistólica e diastólica, em mmHg |
| `fc` | Frequência cardíaca, em bpm |
| `datahora` | Data e hora da medição |
| `movimento_detectado`, `batimento_irregular` | Avisos do próprio aparelho |
| `simulado` | `true` no modo de teste do medidor |

Erros possíveis: 408 (tempo esgotado) e 500 (falha no aparelho, medidor não pareado ou medição já
em andamento). Usa o medidor ativo da tela de configuração (pelo endereço Bluetooth cadastrado ou,
sem endereço, qualquer Omron por perto).

### Saturação do relógio: POST /spo2, POST /api/spo2/iniciar e GET /api/spo2/ultima

O app do Galaxy Watch (`relogio_spo2/`) envia cada medição concluída para `POST /spo2` (sem o
prefixo `/api`, igual ao antigo `server.py` do projeto-spo2), com `{"spo2": 96, "timestamp": 1793017961648}`
(`timestamp` em ms, horário do relógio). Resposta 201 `{"received": true}`; 422 se `spo2` não
estiver entre 0 e 100. A leitura fica guardada (a última) e vai para `backend/dados/spo2_leituras.csv`.

Na tela de medição, o front chama `POST /api/spo2/iniciar`, que devolve
`{"inicio_ms": 1793017961679, "simulado": false}` (no modo de teste, agenda uma leitura falsa para
daqui a 6 s), e consulta `GET /api/spo2/ultima` a cada 2 s:

```json
{ "leitura": { "spo2": 96, "timestamp": 1793017961648, "recebido_em_ms": 1793017961650, "simulado": false } }
```

A leitura vale para a triagem quando `recebido_em_ms >= inicio_ms`. `leitura` é `null` enquanto
nada chegou desde que o backend foi iniciado. Se passar `tempo_spo2_s` sem leitura, a tela pede
para digitar a saturação.

### Login da configuração: POST /api/login e POST /api/logout

As rotas da tela de configuração (`/api/ajustes`, `/api/medidores...`, `GET /api/banco` e
`GET /api/triagens`) exigem o cabeçalho `Authorization: Bearer <token>`; sem ele respondem 401.
As rotas usadas pelo paciente (`/api/config`, `/api/classificar`, `/api/spo2/...`,
`/api/triagens/encaminhamento` etc.) continuam abertas.

`POST /api/login` recebe `{"email", "senha"}` de um usuário da tabela `usuario` com perfil `ADMIN` e
devolve `{"token", "nome", "email"}`. Erros: 401 com a mensagem para a tela ("E-mail ou senha
incorretos.", "Só administradores podem acessar a configuração.", usuário bloqueado após 5 senhas
erradas) e 503 se o banco estiver desligado. O token vale 8 horas (ou até o backend reiniciar).
`POST /api/logout` (com o cabeçalho) encerra a sessão e responde 204.

### Câmera: /api/presenca (mesma pessoa do começo ao fim)

| Rota | O que faz |
|---|---|
| `POST /api/presenca/iniciar` | Chamada ao começar a triagem: liga a câmera; o primeiro rosto vira o titular |
| `GET /api/presenca` | `{"sessao", "estado", "mensagem", "simulado", "ausente_s"}`; o front consulta a cada 1 s na conversa e na medição |
| `POST /api/presenca/encerrar` | Desliga a câmera (conclusão, reinício ou volta à identificação); 204 |
| `POST /api/presenca/simular` | Só administradores, no modo de teste da câmera: `{"evento": "sair" \| "voltar" \| "trocar"}`; 409 sem triagem simulada em andamento |
| `GET /api/camera/testar?indice=0` | Só administradores: `{"ok", "mensagem", "rostos"}` (abre a câmera e conta os rostos; não guarda imagem) |
| `POST /api/triagens/cancelada` | Grava a triagem cancelada: `{"paciente", "perfil", "motivo"}` -> `{"triagem_id"}` |

`estado`: `aguardando_rosto` (ainda não viu ninguém), `presente`, `ausente` (o titular saiu; a tela
mostra o aviso), `cancelada` (outra pessoa ficou no lugar por `tempo_troca_s`, ou o titular sumiu por
`tempo_abandono_s`), `erro` (câmera não abriu; a triagem segue sem conferência) e `desligado`.
Quando recebe `cancelada`, o front para a conversa, chama `/api/triagens/cancelada` e mostra a tela
de cancelamento. `/api/config` traz `usar_camera` e `camera_simulada`; os ajustes da câmera
(`usar_camera`, `modo_teste_camera`, `camera_indice`, `limiar_camera`, `tempo_troca_s`,
`tempo_abandono_s`) ficam em `/api/ajustes`.

### Usuários: /api/usuarios (só administradores)

| Rota | O que faz |
|---|---|
| `GET /api/usuarios` | Lista `[{"id", "nome", "email", "perfil", "ativo", "tentativas_invalidas", "criado_em"}]` |
| `POST /api/usuarios` | Cadastra `{"nome", "email", "senha", "perfil"}` (senha com 8+ caracteres; perfil `ADMIN`, `GESTOR` ou `ATENDENTE`). 201 com o usuário; 409 se o e-mail já existe |
| `PATCH /api/usuarios/{id}` | `{"ativo": false}` bloqueia (derruba as sessões abertas dele); `{"ativo": true}` desbloqueia e zera as senhas erradas. 409 ao tentar bloquear o próprio usuário ou o último administrador ativo; 404 se não existe |

Todas respondem 503 se o banco estiver desligado.

### Tela de configuração: /api/ajustes e /api/medidores

`GET /api/ajustes` devolve:

```json
{
  "modo_teste_pressao": false,
  "modo_teste_spo2": false,
  "usar_medidor": true,
  "usar_relogio": true,
  "tempo_pressao_s": 120,
  "tempo_spo2_s": 90,
  "spo2": 98,
  "temp": 36.5,
  "medidores": [
    { "id": "omron-padrao", "nome": "Omron do totem", "modelo": "omron_hem7156t", "endereco": null, "pareado": true }
  ],
  "medidor_ativo": "omron-padrao",
  "modelos": { "omron_hem7156t": "Omron HEM-7156T", "omron_blesmart": "Outro Omron BLEsmart (HEM-71xxT)" },
  "url_relogio": "http://192.168.15.9:8000/spo2"
}
```

`PUT /api/ajustes` recebe só os campos a mudar (os mesmos acima, menos `medidores`, `modelos` e
`url_relogio`) e devolve o objeto completo. Faixas: tempos de 20 a 600 s, `spo2` de 50 a 100,
`temp` de 30 a 45. 404 se `medidor_ativo` não existir.

| Rota | O que faz |
|---|---|
| `GET /api/medidores/procurar` | Escaneia o Bluetooth por 8 s e lista os Omron: `[{"nome", "endereco", "rssi"}]` |
| `POST /api/medidores` | Cadastra `{"nome", "modelo", "endereco"}` (endereço opcional, `AA:BB:CC:DD:EE:FF`); 201 com o medidor |
| `POST /api/medidores/{id}/parear` | Programa a chave no aparelho (precisa estar com o "P" piscando); devolve o medidor com `pareado: true` e o endereço. 408 se não achar o aparelho em 20 s |
| `DELETE /api/medidores/{id}` | Remove o medidor e devolve os ajustes (se era o ativo, o primeiro da lista vira o ativo) |

No modo de teste do medidor, procurar e parear são simulados (não usam o Bluetooth).

### Banco de dados: /api/banco e /api/triagens

| Rota | O que faz |
|---|---|
| `GET /api/banco` | `{"banco", "servidor", "conectado", "erro", "total_triagens", "salvar_no_banco"}`; tenta conectar na hora |
| `GET /api/triagens?limite=10` | Últimas triagens: `id`, `data_hora_inicio`, `status`, `modo_questionario`, `paciente`, `cor`, `nivel`, `motivo`. 503 se o banco estiver fora |
| `POST /api/triagens/encaminhamento` | Grava quem foi encaminhado direto à enfermagem: `{"paciente", "perfil", "motivos"}`; devolve `{"triagem_id"}` (`null` se não gravou) |

As triagens concluídas não têm rota própria: são gravadas por `POST /api/classificar` quando a
requisição traz `registro`. Esquema do banco: `banco/schema.sql`.

Se a medição falhar, a tela deixa o usuário digitar os valores; nesse caso o front pula esta rota
e vai direto para `/api/classificar`.

### POST /api/classificar

Manda os sintomas e os sinais vitais para a árvore de decisão e devolve a classificação.

Requisição:

```json
{
  "sintomas": ["dor_toracica", "sudorese_fria"],
  "pas": 128,
  "pad": 82,
  "fc": 76,
  "spo2": 98,
  "temp": 36.5,
  "explicar": true,
  "perfil": { "idade": 70, "sexo": "F", "deficiencias": ["visual"] }
}
```

| Campo | Significado |
|---|---|
| `sintomas` | Chaves do catálogo da árvore |
| `pas`, `pad`, `fc` | Valores da medição de pressão |
| `pulso_irregular` | Opcional (`false`); `true` quando o Omron avisou batimento irregular: é "pulso anormal" no Manchester (laranja; com PAS < 90, vermelho) |
| `spo2`, `temp` | Opcionais; sem valor, o backend usa os do `.env` |
| `explicar` | `true` no modo clássico (a LLM escreve a explicação); `false` no tempo real |
| `perfil` | Opcional; idade, sexo e deficiências (veja "Perfil do paciente") |
| `registro` | Opcional; dados para gravar a triagem no banco (veja abaixo). Sem ele, nada é gravado |

`registro`:

```json
{
  "paciente": { "nome": "MARIA DA SILVA", "cpf": "529.982.247-25", "data_nascimento": "10/02/1956" },
  "modo_questionario": "VOZ",
  "resumo": "Febre e tosse há dois dias",
  "conversa": [{ "role": "user", "content": "Estou com febre e tosse" }],
  "pressao_origem": "SENSOR", "pressao_experimental": false,
  "spo2_origem": "SENSOR", "spo2_experimental": false
}
```

`*_origem` é `SENSOR` (veio do aparelho) ou `MANUAL` (digitado); `*_experimental` é `true` quando o
valor veio do modo de teste. Se o banco estiver desligado ou o CPF for inválido, a classificação
funciona normalmente e só `triagem_id` volta `null`.

Resposta (além de `resultado` e `texto`, vem `triagem_id`: o id da triagem gravada, ou `null`):

```json
{
  "resultado": {
    "cor": "LARANJA",
    "prioridade": "Muito urgente",
    "tempo_alvo_min": 10,
    "orientacao": "Precisa de atendimento médico em até 10 minutos.",
    "nivel": "N5",
    "motivo": "Dor no peito com sinais associados (possível síndrome coronariana)",
    "outros_achados": [
      { "cor": "AMARELO", "nivel": "N5", "motivo": "Sintoma moderado: Dor no peito, Suor frio" }
    ],
    "atendimento_prioritario": true,
    "motivos_prioridade": ["Deficiência visual", "Pessoa idosa (70 anos)"],
    "observacoes": [],
    "news2": { "total": 0, "pontos": { "fc": 0, "pas": 0, "spo2": 0, "temp": 0 } },
    "dados": {
      "vitais": { "pas": 128, "pad": 82, "fc": 76, "spo2": 98, "temp": 36.5 },
      "sintomas": ["dor_toracica", "idoso", "sudorese_fria"],
      "perfil": { "idade": 70, "sexo": "F", "deficiencias": ["visual"] }
    }
  },
  "texto": "Sua classificação é laranja, muito urgente..."
}
```

`resultado` é exatamente o que `arvore_decisao.classificar_risco` devolve. `atendimento_prioritario` não muda a cor: indica que a pessoa deve ser atendida antes, dentro da mesma cor. `observacoes` traz avisos sobre o perfil, como chaves ignoradas pelo sexo ou os limites de pulso e o NEWS2 serem de adultos em menores de 16 anos. `texto` é a explicação
falada; vem `null` quando `explicar` é `false`. Se a OpenAI falhar na explicação, o backend
monta uma frase padrão a partir do resultado, sem devolver erro.

Erros possíveis: 422 (sinal vital fora da faixa ou sintoma desconhecido).

## Fora desta API

No modo tempo real, a voz vai do navegador direto para a OpenAI (`useRealtime.js`), usando a chave
de `/api/realtime`. Essa conexão não passa pelo backend e não faz parte deste contrato.
