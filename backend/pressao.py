"""
Leitura da pressão arterial (Omron HEM-7156T) durante a triagem.

Reaproveita o código da pasta "pressao_arterial" (omron_ble.py e 4_background_reader.py).

Fluxo de `medir_pressao(tempo_s)`:
  - Marca o horário de início e fica conectando/consultando o aparelho até aparecer
    uma medição NOVA (feita depois do início) ou até acabar o tempo.
  - "Nova" = registro que não existia na 1ª leitura da sessão, OU com data/hora do
    aparelho >= início - 2 min (caso a 1ª leitura já pegue a medição pronta).

Pré-requisito: o medidor ativo estar pareado (tela de configuração > Parear, ou
`3_read_latest_measurement.py`; a chave fica em omron_pairing_key.json).
Não rode o `4_background_reader.py` ao mesmo tempo que o servidor.

O modo de teste e o medidor usado vêm de ajustes.py (tela de configuração). Também ficam aqui
`procurar_medidores()` (lista os Omron por perto) e `parear()` (programa a chave num aparelho novo).
"""
from __future__ import annotations

import asyncio
import datetime
import importlib
import logging
import random
from typing import Any

import ajustes

log = logging.getLogger("pressao")

# Só um processo pode falar com o aparelho por vez
_trava = asyncio.Lock()


def _chave(r: dict) -> tuple:
    return (r["datetime"], r["sys"], r["dia"], r["bpm"])


def _formatar(r: dict) -> dict[str, Any]:
    return {
        "pas": r["sys"], "pad": r["dia"], "fc": r["bpm"],
        "datahora": r["datetime"].isoformat(),
        "movimento_detectado": r["movimento_detectado"],
        "batimento_irregular": r["batimento_irregular"],
    }


async def medir_pressao(tempo_s: float) -> dict[str, Any]:
    if _trava.locked():
        raise RuntimeError("Já existe uma leitura de pressão em andamento.")
    async with _trava:
        if ajustes.ler()["modo_teste_pressao"]:
            return await _medir_simulado()
        return await _medir_omron(tempo_s, ajustes.medidor_ativo())


async def _medir_simulado() -> dict[str, Any]:
    """Modo de teste sem o aparelho (ligado na tela de configuração ou OMRON_SIMULADO=1 no .env)."""
    await asyncio.sleep(8)
    pas = random.randint(105, 150)
    return {"pas": pas, "pad": pas - random.randint(35, 55), "fc": random.randint(60, 100),
            "datahora": datetime.datetime.now().isoformat(timespec="seconds"),
            "movimento_detectado": False, "batimento_irregular": False, "simulado": True}


def _filtro(bg, medidor: dict | None):
    """Reconhece o medidor no anúncio Bluetooth: pelo endereço cadastrado ou, sem endereço, qualquer Omron."""
    endereco = (medidor or {}).get("endereco")

    def combina(device, adv_data) -> bool:
        if endereco:
            return device.address.upper() == endereco
        return bg._matches_omron(device, adv_data)

    return combina


async def _medir_omron(tempo_s: float, medidor: dict | None) -> dict[str, Any]:
    from bleak import BleakScanner
    from omron_ble import OmronBleLink, read_all_records
    bg = importlib.import_module("4_background_reader")  # nome começa com número -> importlib

    if medidor is None:
        raise RuntimeError("Nenhum medidor de pressão cadastrado. Cadastre um na tela de configuração.")
    chave = bg.load_saved_key()
    if chave is None or not medidor.get("pareado"):
        raise RuntimeError(f"O medidor '{medidor['nome']}' ainda não foi pareado. Pareie na tela de configuração.")
    filtro = _filtro(bg, medidor)

    loop = asyncio.get_running_loop()
    fim = loop.time() + tempo_s
    inicio = datetime.datetime.now()
    limite_data = inicio - datetime.timedelta(minutes=2)
    base: set[tuple] | None = None  # registros que já existiam antes da medição

    def restante() -> float:
        return fim - loop.time()

    while restante() > 0:
        device = await BleakScanner.find_device_by_filter(filtro, timeout=min(10.0, max(restante(), 1)))
        if device is None:
            continue
        log.info("Omron encontrado (%s). Conectando...", device.address)
        try:
            client = await bg.connect_with_os_pairing_if_needed(device)
        except Exception as exc:  # noqa: BLE001
            log.warning("Falha ao conectar: %s", exc)
            await asyncio.sleep(2)
            continue
        try:
            if not await bg.wait_services_resolved(client):
                continue
            link = OmronBleLink(client)
            await link.unlock(chave)
            while client.is_connected and restante() > 0:
                await link.start_transmission()
                try:
                    registros = await read_all_records(link, user_index=0)
                finally:
                    await link.end_transmission()

                novos = [r for r in registros
                         if r["datetime"] >= limite_data or (base is not None and _chave(r) not in base)]
                if base is None:
                    base = {_chave(r) for r in registros}
                if novos:
                    ultimo = max(novos, key=lambda r: r["datetime"])
                    bg.process_new_records(registros)  # mantém o CSV/histórico atualizado
                    log.info("Medição nova: %s/%s mmHg, %s bpm", ultimo["sys"], ultimo["dia"], ultimo["bpm"])
                    return _formatar(ultimo)
                await asyncio.sleep(4)
        except Exception as exc:  # noqa: BLE001
            log.warning("Erro na sessão com o Omron: %s", exc)
            await asyncio.sleep(2)
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    raise TimeoutError("Tempo esgotado: nenhuma medição nova chegou do medidor de pressão.")


async def procurar_medidores(tempo_s: float = 8.0) -> list[dict[str, Any]]:
    """Escaneia o Bluetooth e lista os medidores Omron por perto (para cadastrar um novo)."""
    if ajustes.ler()["modo_teste_pressao"]:
        await asyncio.sleep(1)
        return [{"nome": "BLEsmart_SIMULADO", "endereco": "00:11:22:33:44:55", "rssi": -50}]
    from bleak import BleakScanner
    bg = importlib.import_module("4_background_reader")

    encontrados = await BleakScanner.discover(timeout=tempo_s, return_adv=True)
    return [{"nome": d.name or adv.local_name or "Omron", "endereco": d.address.upper(), "rssi": adv.rssi}
            for d, adv in encontrados.values() if bg._matches_omron(d, adv)]


async def parear(medidor: dict[str, Any], tempo_s: float = 20.0) -> str:
    """
    Pareia um medidor novo: conecta e programa a chave (o mesmo que o 1º pareamento do app oficial).
    O aparelho precisa estar em modo de pareamento (segure o botão Bluetooth até o "P" piscar).
    Devolve o endereço Bluetooth do aparelho pareado.
    """
    if _trava.locked():
        raise RuntimeError("O medidor está ocupado com uma leitura de pressão.")
    async with _trava:
        if ajustes.ler()["modo_teste_pressao"]:
            await asyncio.sleep(2)
            return medidor.get("endereco") or "00:11:22:33:44:55"
        from bleak import BleakScanner
        from omron_ble import DEFAULT_PAIRING_KEY, OmronBleLink
        bg = importlib.import_module("4_background_reader")

        device = await BleakScanner.find_device_by_filter(_filtro(bg, medidor), timeout=tempo_s)
        if device is None:
            raise TimeoutError("Medidor não encontrado. Segure o botão Bluetooth dele até o \"P\" piscar e tente de novo.")
        log.info("Pareando com %s (%s)...", device.name, device.address)
        client = await bg.connect_with_os_pairing_if_needed(device)
        try:
            if not await bg.wait_services_resolved(client):
                raise RuntimeError("O aparelho não respondeu como um Omron BLEsmart. Tente de novo.")
            await OmronBleLink(client).program_new_key(DEFAULT_PAIRING_KEY)
            bg.save_key(DEFAULT_PAIRING_KEY)
            return device.address.upper()
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
