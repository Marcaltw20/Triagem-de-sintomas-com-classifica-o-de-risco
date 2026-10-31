"""
3_read_latest_measurement.py

Script de exemplo: conecta no HEM-7156T, desbloqueia o aparelho (ou
programa uma chave nova se for a primeira vez), le os registros
armazenados e mostra a leitura mais recente.

Fluxo:
  - 1a execucao: nao existe omron_pairing_key.json -> chama program_new_key()
    (equivalente ao 1o pareamento do app oficial) e salva a chave usada.
  - proximas execucoes: le a chave salva e chama unlock() com ela.

Como usar:
    python 3_read_latest_measurement.py

IMPORTANTE: antes de usar os valores lidos aqui no seu pipeline de
triagem, rode validar_com_visor() (ou simplesmente compare visualmente) e
confirme que sys/dia/bpm batem com o que o aparelho mostra no proprio
visor. O layout de memoria usado (HEM71XXT_PROFILE, em 2_omron_ble.py) foi
copiado do HEM-7155T por ser o mais proximo documentado -- ainda nao foi
confirmado bit-a-bit para o HEM-7156T.
"""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import platform
from typing import Optional

from bleak import BleakClient, BleakScanner



from omron_ble import OmronBleLink, PARENT_SERVICE_UUID, DEFAULT_PAIRING_KEY, read_all_records

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("read_latest_measurement")

KEY_FILE = pathlib.Path(__file__).with_name("omron_pairing_key.json")


def load_saved_key() -> Optional[bytes]:
    if not KEY_FILE.exists():
        return None
    data = json.loads(KEY_FILE.read_text())
    return bytes.fromhex(data["key_hex"])


def save_key(key: bytes) -> None:
    KEY_FILE.write_text(json.dumps({"key_hex": key.hex()}, indent=2))
    log.info("chave salva em %s -- guarde este arquivo junto do projeto.", KEY_FILE)


async def find_device(timeout_s: float = 15.0):
    def _match(device, adv_data):
        name = device.name or (adv_data.local_name if adv_data else None)
        return bool(name and name.startswith("BLEsmart_"))

    return await BleakScanner.find_device_by_filter(_match, timeout=timeout_s)


async def wait_services_resolved(client: BleakClient, tries: int = 20, interval_s: float = 0.25) -> bool:
    for _ in range(tries):
        if PARENT_SERVICE_UUID in [s.uuid for s in client.services]:
            return True
        await asyncio.sleep(interval_s)
    return False


async def connect_with_os_pairing_if_needed(device, max_attempts: int = 3) -> BleakClient:
    """
    Conecta no aparelho e, SO no Windows, pareia com o SO (client.pair()) antes
    de mexer em qualquer characteristic criptografada.

    Por que isso e necessario apesar do resto do codigo evitar pair(): no
    Linux (BlueZ), o "Security Request" que o aparelho dispara ao habilitar
    notify no canal RX/unlock e resolvido de forma transparente, sem popup e
    sem deixar bond salvo -- e por isso o omblepy (feito em Linux) nunca
    precisa chamar pair(). No Windows, o backend WinRT do bleak so ENTREGA
    notificacoes de characteristics que exigem link criptografado depois que
    existe um bond de verdade; sem isso, a notificacao e descartada em
    silencio (sem erro nenhum) -- e foi exatamente esse o sintoma: o write
    funcionou, mas a resposta nunca chegou, ate estourar timeout.

    O pair() do WinRT tem bugs conhecidos (bleak issues #1528, #1788, #1880)
    onde a 1a tentativa derruba a conexao. Por isso reconectamos e tentamos
    de novo ate max_attempts vezes.
    """
    is_windows = platform.system() == "Windows"
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        client = BleakClient(device)
        await client.connect()
        if not is_windows:
            return client
        try:
            log.info("Pareando com o SO (necessario no Windows p/ characteristics criptografadas)... "
                      "tentativa %d/%d", attempt, max_attempts)
            await client.pair()
            if client.is_connected:
                return client
            log.warning("pair() derrubou a conexao, tentando de novo...")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("pair() falhou (tentativa %d/%d): %s", attempt, max_attempts, exc)
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(1.5)

    raise RuntimeError(
        "Nao foi possivel parear com o aparelho apos varias tentativas "
        f"(ultimo erro: {last_error}). Tente parear manualmente pelo Windows "
        "em Configuracoes > Bluetooth e dispositivos (com o aparelho em modo "
        "de pareamento) e rode o script de novo."
    )


async def main():
    device = await find_device()
    if device is None:
        log.error("Aparelho nao encontrado. Coloque o HEM-7156T em modo de pareamento e tente de novo.")
        return

    log.info("Conectando em %s (%s)...", device.name, device.address)

    client = await connect_with_os_pairing_if_needed(device)
    try:
        if not await wait_services_resolved(client):
            log.error("Servicos GATT esperados nao apareceram. Talvez nao seja um HEM-7156T, ou o SO "
                      "ainda nao terminou de resolver os servicos -- tente rodar de novo.")
            return

        link = OmronBleLink(client)

        saved_key = load_saved_key()
        if saved_key is None:
            log.info("Nenhuma chave salva encontrada -- programando o aparelho pela primeira vez "
                     "(equivalente ao pareamento do app oficial).")
            log.info("Se o app 'OMRON connect' ainda estiver pareado com este aparelho em algum celular, "
                     "ele pode parar de conseguir ler os dados depois disso.")
            await link.program_new_key(DEFAULT_PAIRING_KEY)
            save_key(DEFAULT_PAIRING_KEY)
        else:
            log.info("Usando chave salva anteriormente para desbloquear o aparelho.")
            await link.unlock(saved_key)

        log.info("Iniciando sessao de leitura...")
        await link.start_transmission()
        try:
            registros_usuario1 = await read_all_records(link, user_index=0)
        finally:
            await link.end_transmission()

        if not registros_usuario1:
            print("Nenhum registro encontrado para o usuario 1.")
            return

        print(f"\n{len(registros_usuario1)} registro(s) encontrado(s) para o usuario 1:\n")
        for r in registros_usuario1:
            print(f"  {r['datetime']:%d/%m/%Y %H:%M:%S}  "
                  f"SYS={r['sys']:3d}  DIA={r['dia']:3d}  BPM={r['bpm']:3d}"
                  f"{'  [movimento detectado]' if r['movimento_detectado'] else ''}"
                  f"{'  [batimento irregular]' if r['batimento_irregular'] else ''}")

        ultimo = registros_usuario1[-1]
        print(f"\n>>> Medicao mais recente: SYS={ultimo['sys']} DIA={ultimo['dia']} "
              f"BPM={ultimo['bpm']} em {ultimo['datetime']:%d/%m/%Y %H:%M:%S}")
        print("\n*** Confira estes valores contra o visor do aparelho antes de usar no seu pipeline! ***")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
