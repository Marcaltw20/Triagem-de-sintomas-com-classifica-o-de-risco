/*
 * Copyright 2026 Samsung Electronics Co., Ltd. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.samsung.health.sensorsdksample.spo2measurement.tracking

import android.content.Context
import android.util.Log
import com.samsung.android.service.health.tracking.ConnectionListener
import com.samsung.android.service.health.tracking.HealthTracker
import com.samsung.android.service.health.tracking.HealthTracker.TrackerEventListener
import com.samsung.android.service.health.tracking.HealthTrackerException
import com.samsung.android.service.health.tracking.HealthTrackingService
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import com.samsung.health.sensorsdksample.spo2measurement.data.ConnectionState
import com.samsung.health.sensorsdksample.spo2measurement.data.DataState
import com.samsung.health.sensorsdksample.spo2measurement.data.LogTags.APP_TAG
import com.samsung.health.sensorsdksample.spo2measurement.data.MessageState
import com.samsung.health.sensorsdksample.spo2measurement.data.SpO2Status
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TrackingManager @Inject constructor(@ApplicationContext private val context: Context) {
    private var healthTrackingService: HealthTrackingService? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var spO2Tracker: HealthTracker? = null
    private var lastUploadedTimestamp: Long? = null
    private val _spO2State =
        MutableStateFlow<DataState<Int?>>(DataState.Initial)
    val spO2State = _spO2State.asStateFlow()
    private val _spO2StatusState = MutableStateFlow(SpO2Status.INITIAL_STATUS)
    val spO2StatusState = _spO2StatusState.asStateFlow()
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState = _connectionState.asStateFlow()
    private val _messageState = MutableSharedFlow<MessageState>(
        replay = 1,
        extraBufferCapacity = 1,
        onBufferOverflow = kotlinx.coroutines.channels.BufferOverflow.DROP_OLDEST
    )
    val messageState = _messageState.asSharedFlow()

    private val connectionListener = object : ConnectionListener {
        override fun onConnectionSuccess() {
            _connectionState.value = ConnectionState.Connected
            if (isSpO2Available() == null) {
                scope.launch {
                    _messageState.emit(MessageState.AvailableTrackerNotInitialized)
                }
            } else isSpO2Available()?.let {
                if (!it) {
                    scope.launch {
                        _messageState.emit(MessageState.TrackingDisabled)
                    }
                }
            }

        }

        override fun onConnectionEnded() {
            _connectionState.value = ConnectionState.Disconnected
        }

        override fun onConnectionFailed(exception: HealthTrackerException) {
            _connectionState.value = ConnectionState.Disconnected
            processTrackerException(exception)
        }
    }

    private val spO2TrackerListener = object : TrackerEventListener {
        override fun onDataReceived(data: MutableList<DataPoint>) {
            data.forEach { dataPoint ->
                val status = dataPoint.getValue(ValueKey.SpO2Set.STATUS)
                val spO2 = dataPoint.getValue(ValueKey.SpO2Set.SPO2)

                _spO2StatusState.value = obtainSpO2Status(status)
                _spO2State.value = DataState.Success(spO2)

                if (
                    status == 2 &&
                    spO2 != null &&
                    lastUploadedTimestamp != dataPoint.timestamp
                ) {
                    lastUploadedTimestamp = dataPoint.timestamp
                    stopSpO2Measurement(isManuallyTriggered = false)
                    scope.launch {
                        SpO2Uploader.upload(spO2, dataPoint.timestamp)
                            .onSuccess {
                                Log.i(APP_TAG, "SpO2 $spO2% sent to Python")
                            }
                            .onFailure { error ->
                                Log.e(APP_TAG, "Could not send SpO2 to Python", error)
                            }
                    }
                }
            }
        }

        override fun onFlushCompleted() {
            Log.i(APP_TAG, "Data flushed")
        }

        override fun onError(error: HealthTracker.TrackerError) {
            Log.e(APP_TAG, error.name)
            if (error == HealthTracker.TrackerError.PERMISSION_ERROR) {
                scope.launch {
                    _messageState.emit(MessageState.PermissionError)
                }
            } else {
                scope.launch {
                    _messageState.emit(MessageState.Error(error.name))
                }
            }
        }
    }

    fun connect() {
        scope.launch {
            try {
                healthTrackingService = HealthTrackingService(connectionListener, context)
                withContext(Dispatchers.Main) {
                    healthTrackingService?.connectService()
                }
            } catch (exception: Exception) {
                withContext(Dispatchers.Main) {
                    _messageState.emit(MessageState.Error(exception.message))
                }
            }
        }
    }

    fun disconnect() {
        healthTrackingService?.let { service ->
            service.disconnectService()
            healthTrackingService = null
            spO2Tracker = null
        }
    }

    fun startSpO2Measurement() {
        if (healthTrackingService == null) {
            _connectionState.value = ConnectionState.Disconnected
            return
        }

        spO2Tracker = initSpO2Tracker()
        spO2Tracker?.setEventListener(spO2TrackerListener) ?: run {
            scope.launch {
                _messageState.emit(MessageState.TrackerNotInitialized)
            }
        }
    }

    fun stopSpO2Measurement(isManuallyTriggered: Boolean) {
        spO2Tracker?.let { tracker ->
            tracker.unsetEventListener()
            if (isManuallyTriggered) {
                _spO2StatusState.value = SpO2Status.STOPPED
            }
        }
    }

    fun isSpO2Available(): Boolean? {
        if (healthTrackingService == null) return false

        var availableTrackers: List<HealthTrackerType>? = null

        availableTrackers =
            healthTrackingService!!.trackingCapability?.supportHealthTrackerTypes

        if (availableTrackers == null) return null

        return availableTrackers.contains(HealthTrackerType.SPO2_ON_DEMAND)
    }

    fun processTrackerException(exception: HealthTrackerException) {
        var hasResolution: Boolean = false

        hasResolution = exception.hasResolution()

        if (hasResolution) {
            scope.launch {
                _messageState.emit(MessageState.ResolvableError(exception))
            }
        } else {
            exception.printStackTrace()
            val errorMessage = exception.message

            scope.launch {
                _messageState.emit(MessageState.Error(errorMessage))
            }
        }
    }

    fun initSpO2Tracker(): HealthTracker? {
        var spO2Tracker: HealthTracker? = null

        spO2Tracker =
            healthTrackingService?.getHealthTracker(HealthTrackerType.SPO2_ON_DEMAND)

        return spO2Tracker
    }

    private fun obtainSpO2Status(status: Int?): SpO2Status = when (status) {
        -6 -> SpO2Status.TIME_OUT
        -5 -> SpO2Status.LOW_SIGNAL
        -4 -> SpO2Status.DEVICE_MOVING
        0 -> SpO2Status.CALCULATING
        2 -> SpO2Status.MEASUREMENT_COMPLETED
        null -> SpO2Status.NOT_SET
        else -> SpO2Status.INITIAL_STATUS
    }
}
