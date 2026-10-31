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
package com.samsung.health.sensorsdksample.spo2measurement

import android.content.Context
import com.samsung.android.service.health.tracking.HealthTracker
import com.samsung.android.service.health.tracking.HealthTrackerCapability
import com.samsung.android.service.health.tracking.HealthTrackerException
import com.samsung.android.service.health.tracking.HealthTrackingService
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.health.sensorsdksample.spo2measurement.tracking.TrackingManager
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.Assert
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

@RunWith(RobolectricTestRunner::class)
class CodelabTests {

    private lateinit var trackingManager: TrackingManager
    private lateinit var context: Context

    @Before
    fun setUp() {
        context = RuntimeEnvironment.getApplication()
        trackingManager = TrackingManager(context)
    }

    @Test
    fun testIsSpO2Available_NotNull() {
        val mockHealthTrackingService = mockk<HealthTrackingService>()
        val mockTrackingCapability = mockk<HealthTrackerCapability>()
        val healthTrackingServiceField =
            TrackingManager::class.java.getDeclaredField("healthTrackingService")
        healthTrackingServiceField.isAccessible = true
        healthTrackingServiceField.set(trackingManager, mockHealthTrackingService)
        every { mockHealthTrackingService.trackingCapability } returns mockTrackingCapability
        every { mockTrackingCapability.supportHealthTrackerTypes } returns listOf(HealthTrackerType.SPO2_ON_DEMAND)

        val isSpO2Available = trackingManager.isSpO2Available()

        Assert.assertNotNull(isSpO2Available)
    }

    @Test
    fun testProcessTrackerException_VerifyHasResolutionCalled() {
        val mockException = mockk<HealthTrackerException>(relaxed = true)
        every { mockException.hasResolution() } returns true

        trackingManager.processTrackerException(mockException)

        verify { mockException.hasResolution() }
    }

    @Test
    fun testInitSpO2HealthTracker_NotNull() {
        val mockHealthTrackingService = mockk<HealthTrackingService>()
        val mockSpO2Tracker = mockk<HealthTracker>()
        every { mockHealthTrackingService.getHealthTracker(HealthTrackerType.SPO2_ON_DEMAND) } returns mockSpO2Tracker
        val healthTrackingServiceField =
            TrackingManager::class.java.getDeclaredField("healthTrackingService")
        healthTrackingServiceField.isAccessible = true
        healthTrackingServiceField.set(trackingManager, mockHealthTrackingService)

        val healthTracker = trackingManager.initSpO2Tracker()

        Assert.assertNotNull(healthTracker)
        Assert.assertEquals(mockSpO2Tracker, healthTracker)
    }
}
