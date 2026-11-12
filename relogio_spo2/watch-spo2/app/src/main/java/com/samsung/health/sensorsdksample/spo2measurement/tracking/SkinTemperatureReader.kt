package com.samsung.health.sensorsdksample.spo2measurement.tracking

import android.content.Context
import android.content.pm.PackageManager
import android.health.connect.HealthPermissions
import android.os.Build
import androidx.core.content.ContextCompat
import com.samsung.android.service.health.tracking.HealthTracker
import com.samsung.android.service.health.tracking.HealthTrackingService
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume
import java.util.concurrent.atomic.AtomicBoolean

data class SkinTemperatureReading(
    val value: Float? = null,
    val timestamp: Long? = null,
    val status: String,
)

object SkinTemperatureReader {
    suspend fun read(service: HealthTrackingService, context: Context): SkinTemperatureReading {
        val permission = if (Build.VERSION.SDK_INT >= 36) {
            HealthPermissions.READ_SKIN_TEMPERATURE
        } else android.Manifest.permission.BODY_SENSORS
        if (ContextCompat.checkSelfPermission(context, permission) != PackageManager.PERMISSION_GRANTED) {
            return SkinTemperatureReading(status = "sem_permissao")
        }
        val supported = service.trackingCapability.supportHealthTrackerTypes
        if (!supported.contains(HealthTrackerType.SKIN_TEMPERATURE_ON_DEMAND)) {
            return SkinTemperatureReading(status = "nao_suportado")
        }
        var tracker: HealthTracker? = null
        return try {
            withContext(Dispatchers.Main) {
                tracker = service.getHealthTracker(HealthTrackerType.SKIN_TEMPERATURE_ON_DEMAND)
            }
            withTimeoutOrNull(30_000) {
                withContext(Dispatchers.Main) {
                    suspendCancellableCoroutine { continuation ->
                        val finished = AtomicBoolean(false)
                        val listener = object : HealthTracker.TrackerEventListener {
                            override fun onDataReceived(data: MutableList<DataPoint>) {
                                for (point in data) {
                                    if (!continuation.isActive) return
                                    val status = point.getValue(ValueKey.SkinTemperatureSet.STATUS)
                                    val value = point.getValue(ValueKey.SkinTemperatureSet.OBJECT_TEMPERATURE)
                                    if (status == 0 && value != null && value.isFinite() && value in -20f..60f) {
                                        if (finished.compareAndSet(false, true)) continuation.resume(SkinTemperatureReading(value, point.timestamp, "ok"))
                                        return
                                    }
                                    if (status == -1) {
                                        if (finished.compareAndSet(false, true)) continuation.resume(SkinTemperatureReading(status = "erro"))
                                        return
                                    }
                                }
                            }
                            override fun onFlushCompleted() {}
                            override fun onError(error: HealthTracker.TrackerError) {
                                if (continuation.isActive && finished.compareAndSet(false, true)) continuation.resume(SkinTemperatureReading(status = "erro"))
                            }
                        }
                        tracker!!.setEventListener(listener)
                    }
                }
            } ?: SkinTemperatureReading(status = "timeout")
        } finally {
            // Libera o sensor antes de iniciar outro tracker sob demanda (SpO2).
            withContext(NonCancellable + Dispatchers.Main) {
                tracker?.unsetEventListener()
            }
        }
    }
}
