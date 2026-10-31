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
package com.samsung.health.sensorsdksample.spo2measurement.viewmodel

import androidx.lifecycle.ViewModel
import com.samsung.health.sensorsdksample.spo2measurement.data.ConnectionState
import com.samsung.health.sensorsdksample.spo2measurement.data.DataState
import com.samsung.health.sensorsdksample.spo2measurement.data.SpO2Status
import com.samsung.health.sensorsdksample.spo2measurement.tracking.TrackingManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject

@HiltViewModel
class MainViewModel @Inject constructor(
    private val trackingManager: TrackingManager
) : ViewModel() {

    val spO2State: StateFlow<DataState<Int?>> = trackingManager.spO2State
    val connectionState: StateFlow<ConnectionState> = trackingManager.connectionState
    val spO2StatusState: StateFlow<SpO2Status> = trackingManager.spO2StatusState
    val messageState = trackingManager.messageState

    override fun onCleared() {
        super.onCleared()
        disconnect()
    }

    fun connect() {
        trackingManager.connect()
    }

    fun disconnect() {
        trackingManager.disconnect()
    }

    fun startSpO2Measurement() {
        trackingManager.startSpO2Measurement()
    }

    fun stopSpO2Measurement(isManuallyTriggered: Boolean = false) {
        trackingManager.stopSpO2Measurement(isManuallyTriggered)
    }
}
