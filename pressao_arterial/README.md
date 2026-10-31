# Leitura BLE do Omron HEM-7156T (protocolo BLESmart)

Scripts para ler medições de pressão arterial do HEM-7156T via Bluetooth LE
em Python, sem depender do app oficial "OMRON connect".

## Contexto

O HEM-7156T usa o protocolo proprietário "BLESmart" da Omron. Ele foi
identificado decodificando o log HCI (btsnoop) real de um pareamento entre
o app oficial e o aparelho, e cruzado com o protocolo documentado pelo
projeto open-source **[omblepy](https://github.com/userx14/omblepy)**
(por userx14), que fez engenharia reversa do mesmo protocolo para vários
modelos da família HEM-7xxxT. **Cite esse projeto na bibliografia do seu
TCC** ao descrever essa parte da metodologia.

O protocolo da Omron em si **não depende de bonding do sistema
operacional** — o "desbloqueio" é feito inteiramente na camada de
aplicação (GATT), escrevendo uma chave em uma characteristic. No Linux
(BlueZ), isso é suficiente e chamar `client.pair()` explicitamente só
atrapalha (aciona a cerimônia nativa do SO, que tem bugs documentados —
veja [bleak issue #1528](https://github.com/hbldh/bleak/issues/1528),
reportado com um Omron HEM-7322T, mesma família do seu aparelho).

**Achado adicional (Windows):** mesmo sem depender de bonding no nível do
protocolo Omron, o **backend WinRT do bleak só entrega notificações de
characteristics que exigem link criptografado depois que existe um bond
de verdade**. No Linux, o "Security Request" que o aparelho dispara ao
habilitar notify no canal de unlock é resolvido de forma transparente
(sem popup, sem bond salvo); no Windows ele não é — a escrita no
characteristic funciona sem erro nenhum, mas a notificação de resposta
nunca chega, e o código estoura timeout com o erro "nao entrou em modo de
programacao de chave". Por isso, `3_read_latest_measurement.py` chama
`client.pair()` **apenas quando `platform.system() == "Windows"`**, com
retry (2-3 tentativas), já que a 1ª tentativa de `pair()` no WinRT às
vezes derruba a conexão (mesmos bugs do #1528, #1788, #1880) mas costuma
funcionar ao reconectar e tentar de novo. Isso não conflita com a
descoberta acima: o pareamento aqui é só para habilitar a criptografia do
link BLE exigida pelo Windows — o desbloqueio em si continua sendo feito
inteiramente via GATT/EEPROM, sem depender do conteúdo desse bond.

## Ordem de execução

1. `pip install -r requirements.txt`
2. Rode `1_test_connection.py` primeiro. Ele só conecta e lista os
   serviços/características GATT, sem ler nada — serve para confirmar que
   a conexão fica estável sem `pair()`. Cole aqui o que aparecer no
   terminal (sucesso ou erro) para a gente ajustar se precisar.
3. Depois de confirmar que a conexão é estável, rode
   `3_read_latest_measurement.py` (que usa `2_omron_ble.py` como módulo).
   Na primeira execução ele "programa" uma chave no aparelho (equivalente
   ao primeiro pareamento do app oficial) e salva em
   `omron_pairing_key.json`; nas próximas, reusa essa chave.
4. Depois de já ter a chave salva (passo acima feito pelo menos uma vez),
   você pode usar `4_background_reader.py` em vez de rodar o script 3 toda
   vez. **Descoberta importante** (via `5_scan_debug.py`): o HEM-7156T
   anuncia por BLE o tempo todo, mesmo sem apertar nenhum botão — só que
   esse anúncio "de standby" carrega o UUID de serviço padrão Bluetooth
   SIG "Blood Pressure" (`00001810-...`) e às vezes o nome vem com
   capitalização diferente (`BLESmart_` em vez de `BLEsmart_`). O botão
   Bluetooth ("segurar até o P piscar") só é necessário para a
   configuração inicial (1ª execução do script 3, que programa a chave) —
   depois disso, o aparelho já está sempre visível e o
   `4_background_reader.py` reconecta sozinho sempre que ele estiver perto,
   sem qualquer interação manual. O aparelho se desconecta sozinho de
   tempos em tempos (comportamento normal dele); quando isso acontece, o
   script volta a escanear e reconecta assim que o aparelho reaparece no
   anúncio de standby. As leituras novas vão sendo acumuladas em
   `leituras_omron.csv` (o controle de "o que já foi sincronizado" fica em
   `omron_last_sync.json`).

## Atenção: validação obrigatória antes de usar em triagem

O layout de memória usado para decodificar SYS/DIA/BPM/data
(`HEM71XXT_PROFILE` em `2_omron_ble.py`) foi copiado do **HEM-7155T**, que
é o modelo documentado mais próximo do seu — mas ainda **não foi
confirmado bit a bit para o HEM-7156T especificamente**. Antes de usar os
valores lidos no seu pipeline de triagem de risco:

1. Faça uma medição real no aparelho.
2. Anote os valores de SYS/DIA/pulso mostrados no visor dele.
3. Rode `3_read_latest_measurement.py` e confira se os valores lidos
   batem exatamente com o visor.
4. Se não baterem, isso indica que os endereços/tamanhos de registro do
   HEM-7156T são diferentes — nesse caso, me manda o resultado que a
   gente ajusta o perfil.

## Avisos importantes

- O aparelho só guarda **uma chave de pareamento por vez** (mesma
  limitação do app oficial: um bond por vez). Depois de rodar o
  pareamento por este script, o app "OMRON connect" pode parar de
  conseguir ler dados até ser pareado de novo nele.
- Se o Windows já tiver uma entrada de pareamento (mesmo que falha) para
  o HEM-7156T em Configurações > Bluetooth e dispositivos, remova-a antes
  de testar — pode deixar resíduo de bond que atrapalha novas tentativas.
- O aparelho precisa estar em modo de pareamento Bluetooth (segure o
  botão Bluetooth dele até o símbolo/"P" começar a piscar) toda vez que
  for conectar.
