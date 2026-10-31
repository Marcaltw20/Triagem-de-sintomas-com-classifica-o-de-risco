import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.hilt.android)
    alias(libs.plugins.devtools.ksp)
}

android {
    namespace = "com.samsung.health.sensorsdksample.spo2measurement"
    compileSdk {
        version = release(36)
    }

    defaultConfig {
        applicationId = "com.samsung.health.sensorsdksample.spo2measurement"
        minSdk = 30
        targetSdk = 36
        versionCode = 2
        versionName = "2.0"

    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    useLibrary("wear-sdk")
    buildFeatures {
        compose = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.JVM_11
        freeCompilerArgs = listOf(
            "-Xdebug",
            "-XXLanguage:+PropertyParamAnnotationDefaultTargetMode"
        )
    }
}

dependencies {
    implementation(files("libs/samsung-health-sensor-api-1.4.1.aar"))
    implementation(libs.play.services.wearable)
    implementation(platform(libs.compose.bom))
    implementation(libs.ui)
    implementation(libs.ui.graphics)
    implementation(libs.ui.tooling.preview)
    implementation(libs.compose.material)
    implementation(libs.compose.foundation)
    implementation(libs.wear.tooling.preview)
    implementation(libs.activity.compose)
    implementation(libs.core.splashscreen)
    implementation(libs.material3.android)
    implementation(libs.compose.material3)
    implementation(libs.lifecycle.common)
    implementation(libs.lifecycle.runtime.compose)
    implementation(libs.core.ktx)
    implementation(libs.activity.ktx)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.ui.test.junit4)
    debugImplementation(libs.ui.tooling)
    debugImplementation(libs.ui.test.manifest)
    implementation(libs.hilt.android)
    androidTestImplementation(libs.hilt.android.testing)
    ksp(libs.hilt.android.compiler)
    kspAndroidTest(libs.hilt.android.compiler)
    testImplementation(libs.robolectric)
    testImplementation(libs.junit)
    testImplementation(libs.mockk)
}
