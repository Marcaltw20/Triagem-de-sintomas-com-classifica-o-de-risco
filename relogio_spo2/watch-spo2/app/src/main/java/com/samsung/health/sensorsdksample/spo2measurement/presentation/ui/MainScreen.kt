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
package com.samsung.health.sensorsdksample.spo2measurement.presentation.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ButtonColors
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Text
import androidx.wear.compose.material3.AlertDialog
import androidx.wear.compose.material3.TextButton
import com.samsung.health.sensorsdksample.spo2measurement.R
import com.samsung.health.sensorsdksample.spo2measurement.data.SpO2Status
import com.samsung.health.sensorsdksample.spo2measurement.presentation.PermissionRationaleType
import com.samsung.health.sensorsdksample.spo2measurement.presentation.theme.AppTypography
import com.samsung.health.sensorsdksample.spo2measurement.presentation.theme.PaddingBig
import com.samsung.health.sensorsdksample.spo2measurement.presentation.theme.PaddingMedium
import com.samsung.health.sensorsdksample.spo2measurement.presentation.theme.PaddingMini
import com.samsung.health.sensorsdksample.spo2measurement.presentation.theme.PaddingSmall
import com.samsung.health.sensorsdksample.spo2measurement.presentation.theme.ProgressWidth
import com.samsung.health.sensorsdksample.spo2measurement.presentation.theme.SpO2MeasurementTheme

@Composable
fun WearApp(
    spO2Value: String,
    spO2Status: SpO2Status,
    startSpO2Measurement: () -> Unit,
    stopSpO2Measurement: () -> Unit,
    permissionRationaleType: PermissionRationaleType? = null,
    onPermissionRationaleConfirm: () -> Unit,
    onPermissionRationaleDismiss: () -> Unit
) {
    SpO2MeasurementTheme {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colors.background),
            contentAlignment = Alignment.Center
        ) {
            Column(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = PaddingBig),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Title(Modifier)

                val subtitle = when (spO2Status) {
                    SpO2Status.MEASUREMENT_COMPLETED -> stringResource(R.string.measurement_completed)
                    SpO2Status.TIME_OUT -> stringResource(R.string.measurement_failed)
                    SpO2Status.STOPPED -> stringResource(R.string.measurement_stopped)
                    SpO2Status.CALCULATING, SpO2Status.LOW_SIGNAL, SpO2Status.DEVICE_MOVING -> stringResource(
                        R.string.measurement_in_progress
                    )

                    else -> ""
                }

                Subtitle(subtitle)
            }

            Result(
                modifier = Modifier.align(Alignment.Center),
                spO2Value
            )

            if (spO2Status.isInProgress()) {
                CircularProgressIndicator(
                    modifier = Modifier
                        .fillMaxSize(),
                    strokeWidth = ProgressWidth,
                    color = MaterialTheme.colors.primary
                )

                Button(
                    stringResource(R.string.stop)
                ) { stopSpO2Measurement() }
            } else {
                Button(
                    stringResource(R.string.start)
                ) { startSpO2Measurement() }
            }
        }

        permissionRationaleType?.let { type ->
            val message = when (type) {
                PermissionRationaleType.BODY_SENSORS -> stringResource(R.string.permission_rationale_body_sensors)
                PermissionRationaleType.SPO2 -> stringResource(R.string.permission_rationale_spo2)
            }

            PermissionRationaleDialog(
                message = message,
                onConfirm = { onPermissionRationaleConfirm() },
                onDismiss = onPermissionRationaleDismiss
            )
        }
    }
}

@Composable
fun Title(modifier: Modifier) {
    Text(
        modifier = modifier
            .padding(top = PaddingBig),
        text = stringResource(R.string.app_title),
        style = AppTypography.headlineMedium,
        textAlign = TextAlign.Center,
        color = MaterialTheme.colors.onBackground
    )
}

@Composable
fun Subtitle(information: String) {
    Text(
        modifier = Modifier
            .padding(top = PaddingSmall),
        text = information,
        style = AppTypography.bodySmall,
        textAlign = TextAlign.Center,
        color = MaterialTheme.colors.secondary
    )
}

@Composable
fun Result(
    modifier: Modifier,
    spO2Value: String
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Text(
            text = spO2Value,
            style = AppTypography.bodyLarge,
            color = MaterialTheme.colors.onBackground
        )

        Text(
            text = stringResource(R.string.percent),
            style = AppTypography.headlineLarge,
            color = MaterialTheme.colors.onBackground
        )
    }
}

@Composable
fun Button(actionName: String, action: () -> Unit) {
    Box(modifier = Modifier.fillMaxSize()) {
        val colors = ButtonColors(
            containerColor = MaterialTheme.colors.primary,
            contentColor = MaterialTheme.colors.onPrimary,
            disabledContentColor = MaterialTheme.colors.onSurface,
            disabledContainerColor = MaterialTheme.colors.surface
        )

        FilledTonalButton(
            modifier = Modifier
                .padding(bottom = PaddingBig)
                .align(Alignment.BottomCenter),
            contentPadding = PaddingValues(horizontal = PaddingMedium, vertical = PaddingMini),
            colors = colors,
            onClick = {
                action()
            }
        ) {
            Text(
                text = actionName,
                style = AppTypography.bodySmall,
                color = colors.contentColor
            )
        }
    }
}

@Composable
fun PermissionRationaleDialog(
    message: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        visible = true,
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = onConfirm) {
                Text(text = stringResource(android.R.string.ok))
            }
        },
        title = { Text(text = stringResource(R.string.permission_rationale_title)) },
        text = { Text(text = message) }
    )
}
