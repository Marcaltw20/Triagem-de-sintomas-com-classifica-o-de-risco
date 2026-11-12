"""Testes de contrato sem chamadas à OpenAI e sem dados reais no banco."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

import api
import spo2
from schemas import ClassificarIn, Spo2RelogioIn
from server import app
from arvore_decisao import classificar_risco


class TemperaturaRelogioTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.csv = Path(self.tempdir.name) / "relogio.csv"
        self.csv_patch = patch.object(spo2, "ARQUIVO_CSV", self.csv)
        self.csv_patch.start()
        self.old_reading = spo2.ultima()
        self.client = TestClient(app)

    def tearDown(self):
        spo2._ultima = self.old_reading
        self.csv_patch.stop()
        self.tempdir.cleanup()

    def test_receber_e_consultar_mesmo_campo(self):
        payload = {"spo2": 97, "timestamp": 12345, "temperatura": 33.7,
                   "temperatura_tipo": "PELE", "temperatura_timestamp": 12300,
                   "temperatura_status": "ok"}
        self.assertEqual(self.client.post("/spo2", json=payload).status_code, 201)
        leitura = self.client.get("/api/spo2/ultima").json()["leitura"]
        self.assertEqual(leitura["temperatura"], 33.7)
        self.assertEqual(leitura["temperatura_tipo"], "PELE")
        self.assertFalse(leitura["simulado"])
        with self.csv.open() as source:
            log = csv.DictReader(source)
            self.assertEqual(log.fieldnames, ["relogio_timestamp_ms", "relogio_horario_utc", "spo2", "recebido_em_utc", "simulado"])
            self.assertEqual(next(log)["spo2"], "97")

    def test_sem_reutilizar_temperatura_anterior(self):
        spo2.registrar(97, 12345, temperatura=33.7, temperatura_timestamp=12300, temperatura_status="ok")
        self.assertEqual(self.client.post("/spo2", json={"spo2": 98, "timestamp": 12400}).status_code, 201)
        self.assertIsNone(self.client.get("/api/spo2/ultima").json()["leitura"]["temperatura"])

    def test_rejeitar_temperatura_sem_timestamp_ou_status(self):
        for extra in ({"temperatura": 33.7}, {"temperatura_status": "ok"},
                      {"temperatura": 33.7, "temperatura_timestamp": 12300, "temperatura_status": "erro"}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValidationError):
                    Spo2RelogioIn(spo2=97, timestamp=12345, **extra)
        with self.assertRaises(ValidationError):
            ClassificarIn(sintomas=[], pas=120, pad=80, fc=70, temp_tipo="PELE")

    def test_temperatura_chega_ao_calculo_existente_sem_conversao(self):
        payload = {"sintomas": [], "pas": 120, "pad": 80, "fc": 70, "spo2": 97,
                   "temp": 33.7, "temp_tipo": "PELE", "temp_timestamp": 12300, "explicar": False}
        with patch.object(api, "classificar_risco", wraps=classificar_risco) as calcular:
            response = self.client.post("/api/classificar", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calcular.call_args.kwargs["temp"], 33.7)
        result = response.json()["resultado"]
        self.assertEqual(result["dados"]["vitais"]["temp"], 33.7)
        self.assertEqual(result["dados"]["temperatura_tipo"], "PELE")
        self.assertEqual(result["news2"]["pontos"]["temp"], 3)

    def test_limites_originais_permanecem(self):
        response = self.client.post("/api/classificar", json={
            "sintomas": [], "pas": 120, "pad": 80, "fc": 70, "spo2": 97,
            "temp": 29, "temp_tipo": "PELE", "temp_timestamp": 12300, "explicar": False,
        })
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
