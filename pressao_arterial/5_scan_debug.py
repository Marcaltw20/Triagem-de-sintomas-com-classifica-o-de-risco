"""
5_scan_debug.py

Script de DIAGNOSTICO, nao de uso normal. Fica escaneando BLE continuamente
e imprime TODO pacote de anuncio vindo do endereco MAC do HEM-7156T (sem
filtrar por nome/UUID como os outros scripts fazem), incluindo RSSI,
service UUIDs anunciados e manufacturer data brutos.

Objetivo: descobrir se o aparelho manda algum sinal por BLE sozinho depois
de uma medicao nova (sem apertar o botao) -- e se sim, como esse pacote se
parece (pra eventualmente ensinar o 4_background_reader.py a reconhece-lo).

Como usar:
    1. Ajuste DEVICE_ADDRESS abaixo se o endereco do seu aparelho for
       diferente (Windows costuma manter o mesmo endereco entre sessoes).
    2. Rode: python 5_scan_debug.py
    3. Deixe rodando. Segure o botao Bluetooth uma vez pra confirmar que o
       script pega o anuncio de pareamento (deve aparecer na hora).
    4. Espere o aparelho desconectar sozinho (normal).
    5. Faca uma medicao nova SEM apertar nenhum botao Bluetooth.
    6. Observe se aparece ALGUMA linha no terminal nos segundos/minutos
       seguintes. Copie e cole a saida completa (ou a ausencia dela) para
       a gente decidir o proximo passo.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

from bleak import BleakScanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scan_debug")

DEVICE_ADDRESS = "00:5F:BF:B3:8B:3E"  # ajuste se o endereco do seu aparelho for outro


def _on_detection(device, adv_data):
    if device.address.upper() != DEVICE_ADDRESS.upper():
        return
    now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"\n[{now}] PACOTE DE {device.address}")
    print(f"    name/local_name : {device.name!r} / {adv_data.local_name!r}")
    print(f"    rssi            : {adv_data.rssi}")
    print(f"    service_uuids   : {adv_data.service_uuids}")
    print(f"    service_data    : {adv_data.service_data}")
    print(f"    manufacturer_data: {adv_data.manufacturer_data}")
    print(f"    tx_power        : {adv_data.tx_power}")


async def main():
    log.info("Escaneando (sem filtro) por pacotes de %s. Ctrl+C para parar.", DEVICE_ADDRESS)
    log.info("Siga os passos do cabecalho do arquivo: pareie uma vez, deixe desconectar sozinho, "
              "depois faca uma medicao nova SEM apertar nada e veja se aparece algo aqui.")
    scanner = BleakScanner(detection_callback=_on_detection)
    await scanner.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await scanner.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuario.")
