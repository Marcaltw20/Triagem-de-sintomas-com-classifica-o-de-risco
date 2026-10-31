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
package com.samsung.health.sensorsdksample.spo2measurement.presentation

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.samsung.health.sensorsdksample.spo2measurement.R
import com.samsung.health.sensorsdksample.spo2measurement.data.ConnectionState
import com.samsung.health.sensorsdksample.spo2measurement.data.DataState
import com.samsung.health.sensorsdksample.spo2measurement.data.MessageState
import com.samsung.health.sensorsdksample.spo2measurement.data.SpO2Status
import com.samsung.health.sensorsdksample.spo2measurement.presentation.ui.WearApp
import com.samsung.health.sensorsdksample.spo2measurement.viewmodel.MainViewModel
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels()
    private lateinit var permissionManager: PermissionManager
    private var permissionRationaleType by mutableStateOf<PermissionRationaleType?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()

        super.onCreate(savedInstanceState)

        setTheme(android.R.style.Theme_DeviceDefault)

        permissionManager = PermissionManager(this)
        if (!permissionManager.isPermissionGranted()) {
            permissionManager.requestPermission()
        }

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.messageState.collect { messageState ->
                    handleMessage(messageState)
                }
            }
        }

        setContent {
            val connectionState by viewModel.connectionState.collectAsStateWithLifecycle()
            val spO2State by viewModel.spO2State.collectAsStateWithLifecycle()
            val spO2Status by viewModel.spO2StatusState.collectAsStateWithLifecycle()

            LaunchedEffect(connectionState) {
                handleConnectionState(connectionState)
            }
            LaunchedEffect(spO2Status) {
                handleSpO2Status(spO2Status)
            }
            val spO2 = obtainSpO2FromState(spO2State)

            WearApp(
                spO2Value = spO2,
                spO2Status = spO2Status,
                startSpO2Measurement = { startSpO2Measurement() },
                stopSpO2Measurement = { viewModel.stopSpO2Measurement(true) },
                permissionRationaleType = permissionRationaleType,
                onPermissionRationaleConfirm = {
                    permissionRationaleType = null
                    permissionManager.requestPermission(
                        onSuccess = { viewModel.startSpO2Measurement() },
                        onFailure = { showMessage(getString(R.string.permission_denied_permanently)) }
                    )
                },
                onPermissionRationaleDismiss = { permissionRationaleType = null }
            )
        }

        viewModel.connect()
    }

    override fun onDestroy() {
        super.onDestroy()
        viewModel.stopSpO2Measurement()
        viewModel.disconnect()
    }

    private fun handleMessage(messageState: MessageState) {
        when (messageState) {
            is MessageState.ResolvableError -> messageState.exception.resolve(this@MainActivity)
            is MessageState.Error -> showMessage(messageState.errorMessage)
            is MessageState.PermissionError -> showMessage(getString(R.string.permission_not_granted))
            is MessageState.TrackerNotInitialized -> showMessage(getString(R.string.tracker_not_initialized))
            is MessageState.TrackingDisabled -> showMessage(getString(R.string.tracker_not_supported))
            is MessageState.AvailableTrackerNotInitialized -> showMessage(getString(R.string.available_tracker_not_initialized))
        }
    }

    private fun handleConnectionState(connectionState: ConnectionState) {
        when (connectionState) {
            is ConnectionState.Connected -> {
                showMessage(getString(R.string.connected_to_hts))
            }

            is ConnectionState.Disconnected -> {
                showMessage(getString(R.string.disconnected_from_hts))
            }
        }
    }

    private fun obtainSpO2FromState(spO2State: DataState<Int?>) =
        when (spO2State) {
            is DataState.Initial -> resources.getString(R.string.empty_value)
            is DataState.Success -> {
                if (spO2State.data == null) {
                    resources.getString(R.string.null_value)
                } else if (spO2State.data > 0) {
                    "${spO2State.data}"
                } else {
                    resources.getString(R.string.empty_value)
                }
            }
        }

    private fun handleSpO2Status(spO2Status: SpO2Status) {
        when (spO2Status) {
            SpO2Status.TIME_OUT -> {
                showMessage(resources.getString(R.string.message_measurement_failed))
                viewModel.stopSpO2Measurement()
            }

            SpO2Status.LOW_SIGNAL -> showMessage(resources.getString(R.string.message_low_signal))
            SpO2Status.DEVICE_MOVING -> showMessage(resources.getString(R.string.message_device_moving))
            SpO2Status.MEASUREMENT_COMPLETED -> viewModel.stopSpO2Measurement()
            SpO2Status.NOT_SET -> showMessage(resources.getString(R.string.status_not_set))
            else -> {}
        }
    }

    private fun startSpO2Measurement() {
        if (permissionManager.isPermissionGranted()) {
            viewModel.startSpO2Measurement()
        } else if (permissionManager.shouldShowRationale()) {
            permissionRationaleType = permissionManager.getRationaleType()
        } else {
            permissionManager.requestPermission(
                onSuccess = { viewModel.startSpO2Measurement() },
                onFailure = { showMessage(getString(R.string.permission_denied_permanently)) }
            )
        }
    }

    private fun showMessage(message: String?) {
        val messageToShow = message ?: resources.getString(R.string.error_other)

        Toast.makeText(this@MainActivity, messageToShow, Toast.LENGTH_SHORT).show()
    }
}

enum class PermissionRationaleType {
    BODY_SENSORS,
    SPO2
}
