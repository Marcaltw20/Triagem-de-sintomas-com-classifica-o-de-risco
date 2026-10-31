"""
Ajustes do totem que podem ser mudados pela tela de configuração (sem reiniciar o backend).

Ficam salvos em backend/ajustes.json. Na primeira vez, os valores iniciais vêm do .env (config.py).

  modo_teste_pressao  True = simula o medidor de pressão (não precisa do aparelho)
  modo_teste_spo2     True = simula o relógio (SpO2 chega sozinho após alguns segundos)
  usar_medidor        False = não há medidor de pressão: a pessoa digita os valores do visor
  usar_relogio        False = não há relógio: a saturação é digitada na tela
  medidores           medidores de pressão cadastrados (ver novo_medidor)
  medidor_ativo       id do medidor usado na triagem
  salvar_no_banco     True = grava cada triagem no MySQL do XAMPP (banco.py)
  usar_camera ...     câmera que cancela a triagem se outra pessoa assumir o totem (presenca.py)
"""
from __future__ import annotations

import json
import threading
import uuid
from typing import Any

import config

ARQUIVO = config.AQUI / "ajustes.json"

MODELOS = {
    "omron_hem7156t": "Omron HEM-7156T",
    "omron_blesmart": "Outro Omron BLEsmart (HEM-71xxT)",
}

_trava = threading.Lock()


def _medidor_inicial() -> dict[str, Any]:
    # o aparelho que já estava pareado antes da tela de configuração existir
    return {"id": "omron-padrao", "nome": "Omron do totem", "modelo": "omron_hem7156t",
            "endereco": None, "pareado": (config.PASTA_PRESSAO / "omron_pairing_key.json").exists()}


def _padrao() -> dict[str, Any]:
    return {
        "modo_teste_pressao": config.OMRON_SIMULADO,
        "modo_teste_spo2": config.SPO2_SIMULADO,
        "usar_medidor": True,
        "usar_relogio": True,
        "salvar_no_banco": config.SALVAR_NO_BANCO,
        "usar_camera": config.USAR_CAMERA,
        "modo_teste_camera": config.CAMERA_SIMULADA,
        "camera_indice": config.CAMERA_INDICE,
        "limiar_camera": config.LIMIAR_CAMERA,
        "tempo_troca_s": config.TEMPO_TROCA_S,
        "tempo_abandono_s": config.TEMPO_ABANDONO_S,
        "tempo_pressao_s": config.TEMPO_PRESSAO_S,
        "tempo_spo2_s": config.TEMPO_SPO2_S,
        "spo2": config.SPO2_MANUAL,
        "temp": config.TEMP_MANUAL,
        "medidores": [_medidor_inicial()],
        "medidor_ativo": "omron-padrao",
    }


def ler() -> dict[str, Any]:
    with _trava:
        dados = _padrao()
        if ARQUIVO.exists():
            try:
                dados.update(json.loads(ARQUIVO.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass  # arquivo corrompido: volta para os valores padrão
        return dados


def salvar(dados: dict[str, Any]) -> dict[str, Any]:
    with _trava:
        ARQUIVO.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    return dados


def atualizar(mudancas: dict[str, Any]) -> dict[str, Any]:
    dados = ler()
    dados.update({k: v for k, v in mudancas.items() if v is not None})
    if not any(m["id"] == dados["medidor_ativo"] for m in dados["medidores"]):
        dados["medidor_ativo"] = dados["medidores"][0]["id"] if dados["medidores"] else None
    return salvar(dados)


def medidor_ativo() -> dict[str, Any] | None:
    dados = ler()
    return next((m for m in dados["medidores"] if m["id"] == dados["medidor_ativo"]), None)


def novo_medidor(nome: str, modelo: str, endereco: str | None) -> dict[str, Any]:
    dados = ler()
    medidor = {"id": uuid.uuid4().hex[:8], "nome": nome.strip(), "modelo": modelo,
               "endereco": (endereco or "").strip().upper() or None, "pareado": False}
    dados["medidores"].append(medidor)
    if dados["medidor_ativo"] is None:
        dados["medidor_ativo"] = medidor["id"]
    salvar(dados)
    return medidor


def alterar_medidor(id_medidor: str, **campos: Any) -> dict[str, Any]:
    dados = ler()
    for m in dados["medidores"]:
        if m["id"] == id_medidor:
            m.update(campos)
            salvar(dados)
            return m
    raise KeyError(id_medidor)


def remover_medidor(id_medidor: str) -> dict[str, Any]:
    dados = ler()
    dados["medidores"] = [m for m in dados["medidores"] if m["id"] != id_medidor]
    return atualizar({"medidores": dados["medidores"]})
