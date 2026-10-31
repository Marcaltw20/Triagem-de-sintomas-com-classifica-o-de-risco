# Relógio (Galaxy Watch 6) — saturação de oxigênio

App do relógio que mede SpO2 e envia cada resultado para o backend da triagem por Wi-Fi.
Veio do `projeto-spo2` (área de trabalho). O antigo `server.py` não é mais usado: quem recebe as
medições agora é o próprio backend (`POST /spo2` em `backend/api.py`), na mesma porta 8000, e as
leituras vão para `backend/dados/spo2_leituras.csv`. As instruções completas originais estão em
`README_original.md`.

Para testar a triagem sem o relógio, ligue "Simular o relógio" na tela de configuração do totem
(engrenagem na identificação), ou desligue "Usar o relógio" para digitar a saturação.

## Instalar no relógio (uma vez)

0. Baixe o Samsung Health Sensor SDK (https://developer.samsung.com/health/sensor/overview.html) e
   coloque o arquivo `samsung-health-sensor-api-1.4.1.aar` em `watch-spo2/app/libs/`. Ele não está
   no repositório porque tem termos de uso próprios da Samsung.
1. Prepare o relógio (opções do desenvolvedor, depuração ADB sem fio e o Dev Mode do Health
   Platform), como descrito em `README_original.md`, seção "Preparar o relógio".
2. Inicie o backend com `--host 0.0.0.0` e abra a tela de configuração do totem. Em "Relógio",
   copie o endereço mostrado (ex.: `http://192.168.15.9:8000/spo2`).
3. Abra `watch-spo2` no Android Studio e coloque esse endereço em `SERVER_URL`, no arquivo
   `watch-spo2/app/src/main/java/com/samsung/health/sensorsdksample/spo2measurement/tracking/SpO2Uploader.kt`.
4. Selecione o relógio no Android Studio e clique em Run. No relógio, permita o acesso ao sensor.

Se o IP do computador mudar, repita os passos 2 a 4. Para o IP não mudar, reserve um IP fixo para o
computador no roteador.

## Usar na triagem

1. Relógio e computador na mesma rede Wi-Fi; backend rodando com `--host 0.0.0.0` (a tarefa
   "Iniciar tudo" do VS Code já faz isso). Permita o Python no firewall do Windows (rede privada).
2. Na tela de medição, a pessoa coloca o relógio no pulso do braço sem a braçadeira, abre o app,
   toca em **Start** e mantém o braço parado (cerca de 30 segundos).
3. Assim que o relógio envia, a saturação aparece na tela e a classificação continua sozinha.

Para conferir a conexão sem fazer uma triagem, meça no relógio com a tela de configuração aberta:
a leitura aparece em "Última leitura recebida".

## Origem e licença

O app adapta o exemplo oficial de medição de SpO2 da Samsung, com o envio HTTP ao backend. Os avisos
de autoria e `watch-spo2/LICENSE.html` foram preservados. A biblioteca Samsung Health Sensor SDK
(`watch-spo2/app/libs/samsung-health-sensor-api-1.4.1.aar`) tem seus próprios termos de uso.
