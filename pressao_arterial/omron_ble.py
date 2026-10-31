"""
2_omron_ble.py

Modulo de comunicacao com monitores de pressao arterial Omron que usam o
protocolo proprietario "BLESmart" via Bluetooth LE (familia HEM-71xxT,
inclui o HEM-7156T).

BASE DO PROTOCOLO: os UUIDs de servico/caracteristica e a sequencia de
comandos usados aqui foram identificados (a) decodificando o log HCI
(btsnoop) real do app oficial "OMRON connect" com o HEM-7156T, e (b)
cruzando com o protocolo documentado pelo projeto open-source omblepy
(https://github.com/userx14/omblepy, de userx14), que fez engenharia
reversa do mesmo protocolo para varios modelos da familia HEM-7xxxT.
Cite esse projeto na bibliografia do TCC ao descrever a integracao BLE -
sem o trabalho de reverse engineering dele, a decodificacao completa dos
comandos binarios (abaixo) teria sido muito mais dificil.

DECISAO DE DESIGN IMPORTANTE: este modulo NUNCA chama client.pair(). O
"desbloqueio" do aparelho e feito inteiramente na camada de aplicacao
(GATT), escrevendo uma chave de 16 bytes na characteristic de "unlock".
Chamar pair() explicitamente no Windows aciona a cerimonia de pareamento
nativa do SO (WinRT), que tem bugs documentados que derrubam a conexao
durante o pareamento (bleak issues #1528, #1788, #1880) - foi
provavelmente a causa do problema original relatado.

ATENCAO (uso em contexto de triagem/saude): a decodificacao dos registros
(campos sys/dia/bpm/data) abaixo usa o layout de memoria conhecido do
HEM-7155T (mesma geracao/protocolo do HEM-7156T), pois o HEM-7156T ainda
nao tem um perfil publicado. Antes de confiar nesses valores no seu
software de triagem, VALIDE: faca uma medicao no aparelho, anote os
valores mostrados no visor dele, e confira se o valor lido por este
codigo bate exatamente. Veja a funcao validar_com_visor() no script
3_read_latest_measurement.py.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field
from typing import Optional

from bleak import BleakClient

log = logging.getLogger("omron_ble")

# ---------------------------------------------------------------------------
# UUIDs do protocolo BLESmart (confirmados byte-a-byte contra o log HCI real)
# ---------------------------------------------------------------------------
PARENT_SERVICE_UUID = "ecbe3980-c9a2-11e1-b1bd-0002a5d5c51b"

RX_CHANNEL_UUIDS = [  # notificacoes: aparelho -> PC
    "49123040-aee8-11e1-a74d-0002a5d5c51b",
    "4d0bf320-aee8-11e1-a0d9-0002a5d5c51b",
    "5128ce60-aee8-11e1-b84b-0002a5d5c51b",
    "560f1420-aee8-11e1-8184-0002a5d5c51b",
]
TX_CHANNEL_UUIDS = [  # escrita: PC -> aparelho
    "db5b55e0-aee7-11e1-965e-0002a5d5c51b",
    "e0b8a060-aee7-11e1-92f4-0002a5d5c51b",
    "0ae12b00-aee8-11e1-a192-0002a5d5c51b",
    "10e1ba60-aee8-11e1-89e5-0002a5d5c51b",
]
UNLOCK_CHAR_UUID = "b305b680-aee7-11e1-a730-0002a5d5c51b"

# Chave padrao (arbitraria) usada para "programar" o aparelho na primeira
# vez, analogo ao pareamento do app oficial. So precisa ser feito uma vez;
# depois disso o aparelho so aceita leituras de quem manda essa mesma chave
# (por isso salvamos ela em disco - veja omron_pairing_key.json).
DEFAULT_PAIRING_KEY = bytes.fromhex("deadbeaf12341234deadbeaf12341234")


class OmronProtocolError(RuntimeError):
    """Erro de protocolo/comunicacao com o aparelho Omron."""


@dataclass
class _RxState:
    buffers: list = field(default_factory=lambda: [None, None, None, None])
    packet_type: Optional[bytes] = None
    eeprom_address: Optional[bytes] = None
    data: Optional[bytes] = None
    finished: bool = False


class OmronBleLink:
    """
    Encapsula a conversa GATT de baixo nivel com o aparelho Omron.

    Uso tipico:
        async with BleakClient(device) as client:
            link = OmronBleLink(client)
            await link.unlock(saved_key)           # ou link.program_new_key(...) na 1a vez
            await link.start_transmission()
            dados = await link.read_eeprom(0x0098, 60 * 0x10)
            await link.end_transmission()
    """

    def __init__(self, client: BleakClient):
        self.client = client
        self._rx = _RxState()
        self._rx_notify_enabled = False
        self._rx_handle_to_channel: dict[int, int] = {}

    # -- reassembly dos canais RX (o protocolo divide pacotes grandes em ate
    #    4 characteristics de 16 bytes cada, e valida com XOR checksum) -----
    def _on_rx_notification(self, sender, raw_bytes: bytearray):
        handle = sender if isinstance(sender, int) else sender.handle
        channel_idx = self._rx_handle_to_channel.get(handle, 0)
        self._rx.buffers[channel_idx] = bytes(raw_bytes)
        log.debug("rx canal%d < %s", channel_idx, raw_bytes.hex())

        if self._rx.buffers[0] is None:
            return
        packet_size = self._rx.buffers[0][0]
        needed_channels = range((packet_size + 15) // 16)
        for idx in needed_channels:
            if self._rx.buffers[idx] is None:
                return  # ainda faltam pedacos

        combined = bytearray()
        for idx in needed_channels:
            combined += self._rx.buffers[idx]
        combined = combined[:packet_size]
        self._rx.buffers = [None, None, None, None]

        xor_crc = 0
        for b in combined:
            xor_crc ^= b
        if xor_crc != 0:
            raise OmronProtocolError(f"checksum XOR invalido no pacote recebido: {combined.hex()}")

        self._rx.packet_type = bytes(combined[1:3])
        self._rx.eeprom_address = bytes(combined[3:5])
        expected_len = combined[5]
        if self._rx.packet_type == bytes.fromhex("8f00"):  # fim de transmissao tem formato especial
            self._rx.data = bytes(combined[6:7])
        elif expected_len > (len(combined) - 8):
            self._rx.data = b"\xff" * expected_len
        else:
            self._rx.data = bytes(combined[6:6 + expected_len])
        self._rx.finished = True

    def _on_unlock_notification(self, _sender, raw_bytes: bytearray):
        self._rx.data = bytes(raw_bytes)
        self._rx.finished = True

    async def _enable_rx_channels(self):
        if self._rx_notify_enabled:
            return
        self._rx_handle_to_channel = {}
        for idx, uuid in enumerate(RX_CHANNEL_UUIDS):
            char = self.client.services.get_characteristic(uuid)
            if char is not None:
                self._rx_handle_to_channel[char.handle] = idx
        for uuid in RX_CHANNEL_UUIDS:
            await self.client.start_notify(uuid, self._on_rx_notification)
        self._rx_notify_enabled = True

    async def _disable_rx_channels(self):
        if not self._rx_notify_enabled:
            return
        for uuid in RX_CHANNEL_UUIDS:
            await self.client.stop_notify(uuid)
        self._rx_notify_enabled = False

    async def _send_command(self, command: bytes, timeout_s: float = 1.0, retries: int = 5):
        """Envia um comando (fragmentado pelos canais TX) e espera resposta nos canais RX."""
        for attempt in range(retries):
            self._rx.finished = False
            remaining = command
            for channel_idx in range((len(command) + 15) // 16):
                chunk = remaining[:16]
                await self.client.write_gatt_char(TX_CHANNEL_UUIDS[channel_idx], chunk)
                remaining = remaining[16:]

            waited = 0.0
            while not self._rx.finished and waited < timeout_s:
                await asyncio.sleep(0.1)
                waited += 0.1
            if self._rx.finished:
                return self._rx.packet_type, self._rx.eeprom_address, self._rx.data
            log.warning("timeout esperando resposta, tentativa %d/%d", attempt + 1, retries)
        raise OmronProtocolError(f"comando {command.hex()} falhou apos {retries} tentativas")

    @staticmethod
    def _with_xor_crc(header_and_data: bytes) -> bytes:
        xor_crc = 0
        for b in header_and_data:
            xor_crc ^= b
        return header_and_data + b"\x00" + bytes([xor_crc])

    # -- desbloqueio / "pareamento" na camada de aplicacao -------------------
    async def program_new_key(self, new_key: bytes = DEFAULT_PAIRING_KEY, max_attempts: int = 10):
        """
        Programa uma NOVA chave de 16 bytes no aparelho. So precisa ser
        chamado uma vez por aparelho (equivalente ao 1o pareamento do app
        oficial). A partir daí, o aparelho so aceita essa chave -- salve-a
        em disco e use unlock() nas proximas execucoes.

        ATENCAO: isso substitui a chave que o app oficial "OMRON connect"
        possa ter programado. Depois disso o app oficial pode nao
        conseguir mais ler dados desse aparelho ate ser pareado de novo.
        """
        if len(new_key) != 16:
            raise ValueError("a chave precisa ter exatamente 16 bytes")

        # habilitar notificacao no 1o canal RX e o que faz o aparelho
        # disparar o pedido de seguranca (Security Request) da camada BLE.
        # o SO (BlueZ/WinRT) resolve esse pedido de forma transparente,
        # sem popup, desde que a gente NAO tenha chamado pair() antes.
        await self.client.start_notify(RX_CHANNEL_UUIDS[0], lambda *_: None)
        await self.client.start_notify(UNLOCK_CHAR_UUID, self._on_unlock_notification)
        try:
            for attempt in range(max_attempts):
                self._rx.finished = False
                await self.client.write_gatt_char(UNLOCK_CHAR_UUID, b"\x02" + b"\x00" * 16, response=True)
                waited = 0.0
                while not self._rx.finished and waited < 2.0:
                    await asyncio.sleep(0.1)
                    waited += 0.1
                response = self._rx.data
                if response is not None and response[:2] == bytes.fromhex("8200"):
                    log.info("modo de programacao de chave ativado (tentativa %d)", attempt + 1)
                    break
                log.debug("tentativa %d/%d: resposta=%s", attempt + 1, max_attempts,
                          response.hex() if response else None)
                await asyncio.sleep(1)
            else:
                raise OmronProtocolError(
                    "nao entrou em modo de programacao de chave. O aparelho esta em "
                    "modo de pareamento (led/simbolo piscando)?"
                )

            self._rx.finished = False
            await self.client.write_gatt_char(UNLOCK_CHAR_UUID, b"\x00" + new_key, response=True)
            waited = 0.0
            while not self._rx.finished and waited < 2.0:
                await asyncio.sleep(0.1)
                waited += 0.1
            response = self._rx.data
            if response is None or response[:2] != bytes.fromhex("8000"):
                raise OmronProtocolError(f"falha ao programar nova chave, resposta={response}")
            log.info("nova chave programada com sucesso.")
        finally:
            await self.client.stop_notify(UNLOCK_CHAR_UUID)
            await self.client.stop_notify(RX_CHANNEL_UUIDS[0])

    async def unlock(self, key: bytes = DEFAULT_PAIRING_KEY):
        """Desbloqueia o aparelho usando uma chave ja programada anteriormente."""
        if len(key) != 16:
            raise ValueError("a chave precisa ter exatamente 16 bytes")
        await self.client.start_notify(UNLOCK_CHAR_UUID, self._on_unlock_notification)
        try:
            self._rx.finished = False
            await self.client.write_gatt_char(UNLOCK_CHAR_UUID, b"\x01" + key, response=True)
            waited = 0.0
            while not self._rx.finished and waited < 3.0:
                await asyncio.sleep(0.1)
                waited += 0.1
            response = self._rx.data
            if response is None or response[:2] != bytes.fromhex("8100"):
                raise OmronProtocolError(
                    "a chave enviada nao confere com a chave programada no aparelho "
                    f"(resposta={response}). Rode o pareamento (program_new_key) de novo?"
                )
        finally:
            await self.client.stop_notify(UNLOCK_CHAR_UUID)

    # -- sessao de leitura de dados -------------------------------------------
    async def start_transmission(self):
        await self._enable_rx_channels()
        packet_type, _addr, _data = await self._send_command(bytes.fromhex("0800000000100018"))
        if packet_type != bytes.fromhex("8000"):
            raise OmronProtocolError(f"resposta inesperada ao iniciar transmissao: {packet_type}")

    async def end_transmission(self):
        packet_type, _addr, data = await self._send_command(bytes.fromhex("080f000000000007"))
        if packet_type != bytes.fromhex("8f00"):
            raise OmronProtocolError(f"resposta inesperada ao encerrar transmissao: {packet_type}")
        if data and data[0] != 0:
            raise OmronProtocolError(f"aparelho reportou erro ao encerrar transmissao: codigo {data[0]}")
        await self._disable_rx_channels()

    async def read_eeprom_block(self, address: int, size: int) -> bytes:
        if size > 16:
            raise ValueError("bloco maximo por leitura e 16 bytes")
        command = bytes.fromhex("080100") + address.to_bytes(2, "big") + size.to_bytes(1, "big")
        command = self._with_xor_crc(command)
        packet_type, rx_addr, data = await self._send_command(command)
        if rx_addr != address.to_bytes(2, "big"):
            raise OmronProtocolError("endereco da resposta nao confere com o solicitado")
        if packet_type != bytes.fromhex("8100"):
            raise OmronProtocolError(f"tipo de pacote inesperado na leitura: {packet_type}")
        return data

    async def read_eeprom(self, start_address: int, total_size: int, block_size: int = 0x10) -> bytes:
        out = bytearray()
        address = start_address
        remaining = total_size
        while remaining > 0:
            chunk_size = min(remaining, block_size)
            out += await self.read_eeprom_block(address, chunk_size)
            address += chunk_size
            remaining -= chunk_size
        return bytes(out)


# ---------------------------------------------------------------------------
# Perfil de memoria conhecido do HEM-7155T (mesma familia/protocolo do
# HEM-7156T). PRECISA SER VALIDADO com o HEM-7156T real antes de confiar
# nos dados -- ver 3_read_latest_measurement.py -> validar_com_visor().
# ---------------------------------------------------------------------------
HEM71XXT_PROFILE = {
    "user_start_addresses": [0x0098, 0x0458],  # usuario 1 e usuario 2
    "records_per_user": [60, 60],
    "record_size_bytes": 0x10,
}


def _bits_to_int(data: bytes, first_bit: int, last_bit: int) -> int:
    """Extrai um campo de bits de um bloco de bytes (big-endian bit order)."""
    big_int = int.from_bytes(data, "little")
    num_bits = (last_bit - first_bit) + 1
    shift = len(data) * 8 - (last_bit + 1)
    mask = (1 << num_bits) - 1
    return (big_int >> shift) & mask


def parse_record(record_bytes: bytes) -> dict:
    """Decodifica um registro de 16 bytes em sys/dia/bpm/data-hora."""
    minute = _bits_to_int(record_bytes, 68, 73)
    second = min(_bits_to_int(record_bytes, 74, 79), 59)
    month = _bits_to_int(record_bytes, 82, 85)
    day = _bits_to_int(record_bytes, 86, 90)
    hour = _bits_to_int(record_bytes, 91, 95)
    year = _bits_to_int(record_bytes, 98, 103) + 2000
    bpm = _bits_to_int(record_bytes, 104, 111)
    dia = _bits_to_int(record_bytes, 112, 119)
    sys_ = _bits_to_int(record_bytes, 120, 127) + 25
    return {
        "sys": sys_,
        "dia": dia,
        "bpm": bpm,
        "movimento_detectado": bool(_bits_to_int(record_bytes, 80, 80)),
        "batimento_irregular": bool(_bits_to_int(record_bytes, 81, 81)),
        "datetime": datetime.datetime(year, month, day, hour, minute, second),
    }


async def read_all_records(link: OmronBleLink, user_index: int = 0) -> list[dict]:
    """Le todos os registros armazenados de um usuario (0 = usuario 1, 1 = usuario 2)."""
    start = HEM71XXT_PROFILE["user_start_addresses"][user_index]
    count = HEM71XXT_PROFILE["records_per_user"][user_index]
    record_size = HEM71XXT_PROFILE["record_size_bytes"]

    raw = await link.read_eeprom(start, count * record_size)
    records = []
    empty_record = b"\xff" * record_size
    for offset in range(0, len(raw), record_size):
        chunk = raw[offset:offset + record_size]
        if chunk == empty_record:
            continue  # slot vazio no buffer circular
        try:
            records.append(parse_record(chunk))
        except Exception as exc:  # noqa: BLE001
            log.warning("nao consegui decodificar registro no offset %d (%s): %s", offset, chunk.hex(), exc)
    records.sort(key=lambda r: r["datetime"])
    return records
