package com.samsung.health.sensorsdksample.spo2measurement.tracking

import java.net.HttpURLConnection
import java.net.URL

object SpO2Uploader {
    // Backend da triagem (triagem_inteligente/backend, rodando com --host 0.0.0.0).
    // O endereço certo aparece na tela de configuração do totem, em "Relógio".
    private const val SERVER_URL = "http://192.168.15.9:8000/spo2"

    fun upload(spo2: Int, timestamp: Long): Result<Unit> = runCatching {
        val json = """{"spo2":$spo2,"timestamp":$timestamp}"""
        val connection = URL(SERVER_URL).openConnection() as HttpURLConnection

        try {
            connection.requestMethod = "POST"
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.connectTimeout = 5_000
            connection.readTimeout = 5_000
            connection.doOutput = true

            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { writer ->
                writer.write(json)
            }

            if (connection.responseCode !in 200..299) {
                error("Python server returned HTTP ${connection.responseCode}")
            }
        } finally {
            connection.disconnect()
        }
    }
}
