"""
1_test_connection.py

Teste de conexao BLE MINIMO com o Omron HEM-7156T, SEM chamar client.pair().

Objetivo deste script: validar a hipotese de que o problema de "desconecta
durante o pareamento" e causado pela chamada explicita a pair() no Windows
(bug conhecido do bleak/WinRT - ver bleak issue #1528, reportado com um
Omron HEM-7322T, mesma familia do HEM-7156T).

Este script SO conecta e lista os servicos/caracteristicas GATT. Nao faz
nenhuma leitura de dados ainda - isso vem na proxima etapa (2_omron_ble.py).

Como usar:
    1. pip install bleak
    2. Coloque o HEM-7156T em modo de pareamento Bluetooth (segure o botao
       Bluetooth do aparelho ate o simbolo Bluetooth/"P" comecar a piscar).
    3. IMPORTANTE: va em Configuracoes > Bluetooth e dispositivos do Windows
       e remova qualquer pareamento antigo do HEM-7156T, se existir (para
       nao competir com uma tentativa de bond "meio feita" anterior).
    4. Rode: python 1_test_connection.py
"""
import asyncio
import logging

from bleak import BleakScanner, BleakClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("test_connection")

# Servico "pai" que todo dispositivo Omron BLESmart expoe. Se ele aparecer
# na lista de servicos, confirmamos que e o mesmo protocolo do log que
# analisamos (b305b680-... / ecbe3980-...).
OMRON_PARENT_SERVICE_UUID = "ecbe3980-c9a2-11e1-b1bd-0002a5d5c51b"
OMRON_UNLOCK_CHAR_UUID = "b305b680-aee7-11e1-a730-0002a5d5c51b"


async def find_device(timeout_s: float = 15.0):
    log.info("Escaneando por dispositivos BLE (%.0fs)... coloque o HEM-7156T em modo de pareamento agora.", timeout_s)

    def _match(device, adv_data):
        name = device.name or (adv_data.local_name if adv_data else None)
        return bool(name and name.startswith("BLEsmart_"))

    device = await BleakScanner.find_device_by_filter(_match, timeout=timeout_s)
    return device


async def main():
    device = await find_device()
    if device is None:
        log.error("Nenhum dispositivo 'BLEsmart_*' encontrado. Verifique se o aparelho esta em modo de "
                   "pareamento (led/simbolo Bluetooth piscando) e dentro do alcance.")
        return

    log.info("Encontrado: %s (%s)", device.name, device.address)

    # ATENCAO: propositalmente NAO chamamos client.pair() em nenhum momento
    # aqui. No Windows isso aciona a cerimonia de pareamento nativa do
    # WinRT, que tem bugs conhecidos (popup com timeout curtissimo, travas
    # de ate 60s, cancelamento mesmo apos aceitar - ver bleak issues #1528,
    # #1788, #1880). O protocolo da Omron nao depende de bonding do SO: o
    # "desbloqueio" e feito na camada de aplicacao via GATT, como veremos
    # no proximo script.
    async with BleakClient(device) as client:
        log.info("Conectado! is_connected=%s", client.is_connected)

        services = client.services
        parent_found = False
        unlock_found = False

        for service in services:
            log.info("Servico: %s", service.uuid)
            if service.uuid.lower() == OMRON_PARENT_SERVICE_UUID.lower():
                parent_found = True
            for char in service.characteristics:
                log.info("    Caracteristica: %s  propriedades=%s", char.uuid, char.properties)
                if char.uuid.lower() == OMRON_UNLOCK_CHAR_UUID.lower():
                    unlock_found = True

        print()
        if parent_found and unlock_found:
            print("*** SUCESSO: servico e caracteristica de 'unlock' da Omron BLESmart encontrados. ***")
            print("*** A conexao ficou estavel sem chamar pair(). Pode seguir para o proximo script. ***")
        else:
            print("Conectou, mas NAO encontrei o servico/caracteristica esperados da Omron.")
            print("Pode ser um dispositivo diferente, ou o GATT ainda nao terminou de resolver -- rode de novo.")

        # segura a conexao por alguns segundos para confirmar que ela
        # nao cai sozinha logo em seguida (o sintoma original relatado)
        log.info("Mantendo conexao por 10s para verificar estabilidade...")
        await asyncio.sleep(10)
        log.info("is_connected apos 10s: %s", client.is_connected)


if __name__ == "__main__":
    asyncio.run(main())
