plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.composeCompiler)
    alias(libs.plugins.detekt)
}

// HRD-701: App signing — secrets from environment, never in repo.
val keystorePath: String? = providers.environmentVariable("KEYSTORE_PATH").orNull
val keystorePassword: String? = providers.environmentVariable("KEYSTORE_PASSWORD").orNull
val keyAlias: String? = providers.environmentVariable("KEY_ALIAS").orNull
val keyPassword: String? = providers.environmentVariable("KEY_PASSWORD").orNull

android {
    namespace = "com.nutriplan.android"
    compileSdk = libs.versions.androidCompileSdk.get().toInt()

    defaultConfig {
        applicationId = "com.nutriplan.android"
        minSdk = libs.versions.androidMinSdk.get().toInt()
        targetSdk = libs.versions.androidTargetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0"

        // HRD-701: Versioning strategy — bump versionCode per release tag.
        // Format: YYYYMMDDNN where NN is build number within the day.
        val buildDate = System.getenv("BUILD_DATE") ?: java.text.SimpleDateFormat(
            "yyyy-MM-dd",
        ).format(java.util.Date())
        buildConfigField("String", "BUILD_DATE", "\"$buildDate\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    signingConfigs {
        create("release") {
            keystorePath?.let { kp ->
                storeFile = file(kp)
                storePassword = keystorePassword ?: ""
                keyAlias = keyAlias ?: ""
                keyPassword = keyPassword ?: ""
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (keystorePath != null) {
                signingConfigs.findByName("release")
            } else {
                // CI uses Play App Signing — upload key provided at submit time.
                // Without a local keystore, fall back to debug config for testing.
                signingConfigs.getByName("debug")
            }

            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(projects.shared)
    implementation(libs.ktor.client.okhttp)

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.foundation)
    implementation(libs.compose.material.icons.extended)
    debugImplementation(libs.compose.ui.tooling)

    // Koin for Android
    implementation(libs.koin.core)
    implementation(libs.koin.compose)
}

detekt {
    buildUponDefaultConfig = true
    config.setFrom(rootProject.files("config/detekt/detekt.yml"))
    // TODO(P0): flip to false once the detekt ruleset is tuned for the team.
    ignoreFailures = true
}
