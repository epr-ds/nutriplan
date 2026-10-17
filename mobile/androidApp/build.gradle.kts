plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.composeCompiler)
    alias(libs.plugins.detekt)
    id("com.google.firebase.crashlytics") version "3.0.5"
}

// HRD-701: App signing — secrets from environment, never in repo.
val keystorePath: String? = providers.environmentVariable("KEYSTORE_PATH").orNull
val keystorePassword: String? = providers.environmentVariable("KEYSTORE_PASSWORD").orNull
val keyAlias: String? = providers.environmentVariable("KEY_ALIAS").orNull
val keyPassword: String? = providers.environmentVariable("KEY_PASSWORD").orNull

// IDN-402: API environment (local/dev/stage/prod) for debug builds. Override with
// -PapiEnv=stage or the API_ENV env var; debug defaults to dev. Release pins prod (below).
val apiEnvironment: String = providers.gradleProperty("apiEnv")
    .orElse(providers.environmentVariable("API_ENV"))
    .getOrElse("dev")

// IDN-505: Google OAuth server (web) client ID. Empty unless provided via -PgoogleServerClientId
// or GOOGLE_SERVER_CLIENT_ID (secrets per env, IDN-803). When blank, the Google button is hidden.
val googleServerClientId: String = providers.gradleProperty("googleServerClientId")
    .orElse(providers.environmentVariable("GOOGLE_SERVER_CLIENT_ID"))
    .getOrElse("")

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
        val buildDate = System.getenv("BUILD_DATE") ?: "unknown"
        buildConfigField("String", "BUILD_DATE", "\"$buildDate\"")

        // IDN-402: API environment (local/dev/stage/prod), see the top-level `apiEnvironment`.
        buildConfigField("String", "API_ENVIRONMENT", "\"$apiEnvironment\"")

        // IDN-505: Google OAuth server client ID (blank ⇒ OAuth buttons hidden).
        buildConfigField("String", "GOOGLE_SERVER_CLIENT_ID", "\"$googleServerClientId\"")
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
            buildConfigField("String", "API_ENVIRONMENT", "\"prod\"")
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

    // IDN-505: Google OAuth via Credential Manager
    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play.services)
    implementation(libs.googleid)

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

    // HRD-602: Firebase Crashlytics for crash/ANR monitoring
    implementation(platform("com.google.firebase:firebase-bom:33.14.0"))
    implementation("com.google.firebase:firebase-crashlytics-ktx")

    // HRD-606: Firebase Analytics for beta funnel/retention instrumentation
    implementation("com.google.firebase:firebase-analytics-ktx")

    // HRD-305: Compose UI testing for accessibility regression checks
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
    debugImplementation(libs.compose.ui.test.manifest)
}

detekt {
    buildUponDefaultConfig = true
    config.setFrom(rootProject.files("config/detekt/detekt.yml"))
    // TODO(P0): flip to false once the detekt ruleset is tuned for the team.
    ignoreFailures = true
}
