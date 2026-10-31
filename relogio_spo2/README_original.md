# Galaxy Watch 6 — SpO2 para Python

O aplicativo mede SpO2 no relógio e envia cada resultado concluído diretamente
ao computador por Wi-Fi. O servidor Python salva as leituras em CSV.

## Requisitos

- Python 3.9 ou superior, sem pacotes adicionais.
- Android Studio com Android SDK 36 e Platform Tools (ADB).
- Galaxy Watch 6 físico, já configurado.
- Relógio e computador na mesma rede Wi-Fi, com comunicação entre dispositivos.

## Preparar o relógio

1. Em Configurações > Sobre o relógio > Informações do software, toque cinco
   vezes em Versão do software para habilitar as opções do desenvolvedor.
2. Em Opções do desenvolvedor, ative Depuração ADB e Depuração sem fio.
3. Em Depuração sem fio > Parear novo dispositivo, anote o IP, a porta de
   pareamento e o código.
4. No terminal, usando o ADB instalado pelo Android Studio, execute
   `adb pair IP:PORTA_DE_PAREAMENTO` e digite o código solicitado.
5. Volte à tela principal de Depuração sem fio e execute
   `adb connect IP:PORTA_DE_CONEXAO`. A porta de conexão costuma ser diferente
   da porta de pareamento. Confirme com `adb devices`.
6. Em Configurações > Aplicativos, abra Health Platform ou Health Sensor
   Service e toque aproximadamente dez vezes no título. Dependendo da versão,
   aparece `[Dev Mode]` ou uma opção Developer mode a ser ativada. Esse modo
   serve para desenvolvimento e testes locais.

No macOS, o ADB costuma estar em
`~/Library/Android/sdk/platform-tools/adb`. Se `adb` não for reconhecido,
substitua o comando por esse caminho completo.

## Configurar o aplicativo

1. Abra a pasta `watch-spo2` no Android Studio e aguarde a sincronização do Gradle.
2. Descubra o IP local do computador. No macOS com Wi-Fi em `en0`, execute
   `ipconfig getifaddr en0`; no Windows, execute `ipconfig`.
3. Abra o arquivo:

   `watch-spo2/app/src/main/java/com/samsung/health/sensorsdksample/spo2measurement/tracking/SpO2Uploader.kt`

4. Altere `SERVER_URL` para `http://IP_DO_COMPUTADOR:8000/spo2`.
5. Selecione o relógio no Android Studio e clique em Run para instalar o app.
6. No relógio, permita o acesso ao sensor solicitado pelo aplicativo.

O SDK da Samsung usado pelo projeto está em
`watch-spo2/app/libs/samsung-health-sensor-api-1.4.1.aar`.
Para obtê-lo separadamente ou consultar seus termos, use o portal oficial:
https://developer.samsung.com/health/sensor/overview.html

## Executar e testar

No terminal, entre na pasta que contém `server.py` e execute:

```bash
python3 server.py
```

No Windows, dependendo da instalação, use `py server.py`.
Mantenha o servidor aberto e permita conexões locais à porta TCP 8000 no
firewall, se necessário. O endereço impresso pelo servidor é o do computador
original; o serviço escuta em todas as interfaces locais na porta 8000.

No relógio, abra o aplicativo, toque em Start e mantenha o braço imóvel até a
medição terminar, normalmente em cerca de 30 segundos. O terminal deverá mostrar
`SpO2 received: 96%`, com o percentual realmente medido.

As leituras serão salvas em `data/spo2_readings.csv`. A pasta e o arquivo são
criados automaticamente no primeiro recebimento. Para parar, pressione Ctrl+C.

Em novos testes, basta iniciar o servidor e medir no relógio. Se o IP do
computador mudar, atualize `SERVER_URL` e reinstale o aplicativo. O SDK fornece
SpO2 sob demanda, não um fluxo contínuo de valores por segundo.

## Origem e licença

O aplicativo adapta o exemplo oficial de medição de SpO2 da Samsung, acrescentando
o envio HTTP ao servidor Python. Os avisos de autoria e o arquivo
`watch-spo2/LICENSE.html` foram preservados. A biblioteca Samsung Health Sensor
SDK possui seus próprios termos de uso.
