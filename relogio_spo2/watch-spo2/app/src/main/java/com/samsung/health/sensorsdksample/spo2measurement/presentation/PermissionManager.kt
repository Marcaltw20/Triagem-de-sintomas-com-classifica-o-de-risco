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

import android.content.pm.PackageManager
import android.health.connect.HealthPermissions
import android.os.Build
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.app.ActivityCompat.shouldShowRequestPermissionRationale
import androidx.core.content.ContextCompat

class PermissionManager(private val activity: ComponentActivity) {

    private var permissionLauncher =
        activity.registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted ->
            if (isGranted) {
                onSuccess()
            } else {
                onFailure()
            }
            clear()
        }

    private var onSuccess: () -> Unit = {}
    private var onFailure: () -> Unit = {}

    fun requestPermission(onSuccess: () -> Unit = {}, onFailure: () -> Unit = {}) {
        this.onSuccess = onSuccess
        this.onFailure = onFailure
        permissionLauncher.launch(getSpO2Permission())
    }

    fun isPermissionGranted() = ContextCompat.checkSelfPermission(
        activity,
        getSpO2Permission()
    ) == PackageManager.PERMISSION_GRANTED

    fun shouldShowRationale(): Boolean =
        shouldShowRequestPermissionRationale(activity, getSpO2Permission())

    fun getRationaleType(): PermissionRationaleType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.BAKLAVA) {
        PermissionRationaleType.SPO2
    } else {
        PermissionRationaleType.BODY_SENSORS
    }

    fun getSpO2Permission(): String {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.BAKLAVA) {
            HealthPermissions.READ_OXYGEN_SATURATION
        } else {
            android.Manifest.permission.BODY_SENSORS
        }
    }

    private fun clear() {
        onSuccess = {}
        onFailure = {}
    }
}
