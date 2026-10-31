"""
4_background_reader.py

Fica escaneando continuamente e conecta sozinho toda vez que o HEM-7156T
estiver por perto -- SEM precisar apertar o botao Bluetooth depois da
configuracao inicial (que so exige ter rodado 3_read_latest_measurement.py
uma vez, para a chave ja estar salva).

Descoberta (via 5_scan_debug.py): o aparelho anuncia por BLE o tempo todo,
mesmo sem apertar nada -- so que com o UUID de servico padrao Bluetooth SIG
"Blood Pressure" (0x1810) e, as vezes, com o nome vindo em capitalizacao
diferente ("BLESmart_..." em vez de "BLEsmart_..."). A versao anterior
deste script so reconhecia o nome com a capitalizacao exata do modo de
pareamento completo, por isso nunca via esse anuncio "de standby" e parecia
exigir apertar o botao toda vez -- na real o aparelho ja estava anunciando,
o script que nao reconhecia.

Fluxo: conecta assim que detecta o aparelho, desbloqueia com a chave salva,
baixa os registros e mantem a conexao aberta consultando por ela a cada
POLL_INTERVAL_S segundos. O proprio aparelho se desconecta sozinho depois
de um tempo (comportamento normal dele, nao e bug) -- quando isso acontece
o script volta a escanear e reconecta sozinho assim que o aparelho
reaparecer no anuncio de standby, sem precisar de nenhuma interacao manual.

Pre-requisito: rode 3_read_latest_measurement.py pelo menos uma vez antes
(precisa existir omron_pairing_key.json com a chave ja programada).

Uso:
    python 4_background_reader.py
    (Ctrl+C para parar)
"""
from __future__ import annotations

import asyncio
import csv
import datetime
import json
import logging
import pathlib
import platform
from typing import Optional

from bleak import BleakClient, BleakScanner

from omron_ble import OmronBleLink, PARENT_SERVICE_UUID, DEFAULT_PAIRING_KEY, read_all_records

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("background_reader")

KEY_FILE = pathlib.Path(__file__).with_name("omron_pairing_key.json")
LOG_FILE = pathlib.Path(__file__).with_name("leituras_omron.csv")
LAST_SYNC_FILE = pathlib.Path(__file__).with_name("omron_last_sync.json")

POLL_INTERVAL_S = 15.0     # de quanto em quanto tempo consulta por novos registros na conexao ja aberta
RECONNECT_WAIT_S = 3.0     # espera entre tentativas depois de uma desconexao


def load_saved_key() -> Optional[bytes]:
    if not KEY_FILE.exists():
        return None
    data = json.loads(KEY_FILE.read_text())
    return bytes.fromhex(data["key_hex"])


def save_key(key: bytes) -> None:
    KEY_FILE.write_text(json.dumps({"key_hex": key.hex()}, indent=2))
    log.info("chave salva em %s", KEY_FILE.name)


def load_last_synced_datetime() -> Optional[datetime.datetime]:
    if not LAST_SYNC_FILE.exists():
        return None
    iso = json.loads(LAST_SYNC_FILE.read_text()).get("last_datetime_iso")
    return datetime.datetime.fromisoformat(iso) if iso else None


def save_last_synced_datetime(dt: datetime.datetime) -> None:
    LAST_SYNC_FILE.write_text(json.dumps({"last_datetime_iso": dt.isoformat()}, indent=2))


def append_to_csv(records: list[dict]) -> None:
    is_new_file = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["datetime", "sys", "dia", "bpm", "movimento_detectado", "batimento_irregular"])
        for r in records:
            writer.writerow([r["datetime"].isoformat(), r["sys"], r["dia"], r["bpm"],
                              r["movimento_detectado"], r["batimento_irregular"]])


def process_new_records(registros: list[dict]) -> int:
    """Grava no CSV so os registros mais novos que o ultimo ja sincronizado."""
    if not registros:
        return 0
    last_synced = load_last_synced_datetime()
    novos = [r for r in registros if last_synced is None or r["datetime"] > last_synced]
    if not novos:
        return 0

    append_to_csv(novos)
    save_last_synced_datetime(max(r["datetime"] for r in registros))

    for r in novos:
        log.info("NOVA LEITURA  %s  SYS=%d DIA=%d BPM=%d%s%s",
                  r["datetime"].strftime("%d/%m/%Y %H:%M:%S"), r["sys"], r["dia"], r["bpm"],
                  "  [movimento]" if r["movimento_detectado"] else "",
                  "  [irregular]" if r["batimento_irregular"] else "")
    return len(novos)


# UUID padrao Bluetooth SIG "Blood Pressure Service" -- confirmado (via
# 5_scan_debug.py) que o HEM-7156T anuncia isso o tempo todo, mesmo sem
# apertar nenhum botao. E esse anuncio "de standby" que permite reconectar
# sem pareamento manual.
BLOOD_PRESSURE_SERVICE_UUID = "00001810-0000-1000-8000-00805f9b34fb"


def _matches_omron(device, adv_data) -> bool:
    # nome vem como "BLEsmart_..." no anuncio de pareamento completo e como
    # "BLESmart_..." (S maiuscula) no anuncio de standby -- por isso
    # comparamos em minusculas, sem depender da capitalizacao exata.
    name = device.name or (adv_data.local_name if adv_data else None)
    if name and name.lower().startswith("blesmart_"):
        return True
    service_uuids = [u.lower() for u in ((adv_data.service_uuids if adv_data else None) or [])]
    return PARENT_SERVICE_UUID.lower() in service_uuids or BLOOD_PRESSURE_SERVICE_UUID.lower() in service_uuids


async def wait_for_device(timeout_s: Optional[float] = None):
    """Escaneia (sem parar, se timeout_s=None) ate encontrar o aparelho anunciando."""
    return await BleakScanner.find_device_by_filter(_matches_omron, timeout=timeout_s or 86400)


async def wait_services_resolved(client: BleakClient, tries: int = 20, interval_s: float = 0.25) -> bool:
    for _ in range(tries):
        if PARENT_SERVICE_UUID in [s.uuid for s in client.services]:
            return True
        await asyncio.sleep(interval_s)
    return False


async def connect_with_os_pairing_if_needed(device, max_attempts: int = 3) -> BleakClient:
    """No Windows, o backend WinRT so entrega notificacoes de characteristics
    criptografadas depois de um bond real, entao precisamos de client.pair()
    (com retry, por causa do bug conhecido do WinRT que derruba a conexao na
    1a tentativa -- bleak issues #1528, #1788, #1880)."""
    is_windows = platform.system() == "Windows"
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        client = BleakClient(device)
        await client.connect()
        if not is_windows:
            return client
        try:
            await client.pair()
            if client.is_connected:
                return client
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(1.5)
    raise RuntimeError(f"nao foi possivel parear com o aparelho (ultimo erro: {last_error})")


async def run_session(device) -> None:
    """Conecta, desbloqueia, e fica consultando por essa MESMA conexao (sem
    desconectar) ate ela cair sozinha."""
    client = await connect_with_os_pairing_if_needed(device)

    try:
        if not await wait_services_resolved(client):
            log.warning("Servicos GATT nao apareceram a tempo -- abortando esta sessao.")
            return

        link = OmronBleLink(client)
        saved_key = load_saved_key()
        if saved_key is None:
            log.info("Nenhuma chave salva -- programando o aparelho pela primeira vez.")
            await link.program_new_key(DEFAULT_PAIRING_KEY)
            save_key(DEFAULT_PAIRING_KEY)
        else:
            await link.unlock(saved_key)

        log.info("Conectado e desbloqueado. Consultando a cada %.0fs. Novas medicoes serao "
                  "detectadas sozinhas -- nao precisa apertar o botao Bluetooth.", POLL_INTERVAL_S)

        while client.is_connected:
            try:
                await link.start_transmission()
                try:
                    registros = await read_all_records(link, user_index=0)
                finally:
                    await link.end_transmission()
                n = process_new_records(registros)
                if n:
                    log.info("%d leitura(s) nova(s) sincronizada(s) em %s.", n, LOG_FILE.name)
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao consultar o aparelho (conexao continua aberta, tentando de novo): %s", exc)
                if not client.is_connected:
                    break

            await asyncio.sleep(POLL_INTERVAL_S)
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def main():
    log.info("Escutando o HEM-7156T -- ele deve aparecer sozinho (anuncia continuamente, "
              "nao precisa apertar o botao Bluetooth). Se nunca conectar, segure o botao "
              "ate o simbolo/\"P\" piscar uma vez para garantir.")
    log.info("Leituras novas serao gravadas em %s. Ctrl+C para parar.", LOG_FILE.name)

    while True:
        try:
            device = await wait_for_device()
            log.info("Aparelho encontrado: %s (%s). Conectando...", device.name, device.address)
            await run_session(device)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Erro na sessao: %s", exc)

        log.info("Conexao encerrada -- voltando a escanear (o aparelho deve reaparecer sozinho).")
        await asyncio.sleep(RECONNECT_WAIT_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuario.")
