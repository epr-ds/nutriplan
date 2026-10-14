# HRD-701: ProGuard / R8 rules for NutriPlan Android release build.
# Tune these rules per release; start conservative and strip aggressively later.

# Keep model classes used by Ktor serialization
-keep class com.nutriplan.shared.model.** { *; }
-keep class com.nutriplan.shared.domain.** { *; }

# Keep Koin injection metadata
-keep class org.koin.** { *; }
-keepclasseswithmembers class * {
    @org.koin.core.annotation.Injected *;
}

# Compose — keep generated classes
-keep class androidx.compose.foundation.** { *; }
-keep class androidx.compose.material3.** { *; }
-keep class androidx.compose.runtime.** { *; }
-keep class androidx.compose.ui.** { *; }

# Retrofit / Ktor networking
-dontwarn okio.**
-dontwarn okhttp3.**
-dontwarn okio.**

# Kotlin coroutines
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}

# Keep BuildConfig fields (version info)
-keep class com.nutriplan.android.BuildConfig { *; }

# Keep R class references
-dontnote android.R.class
-dontnote androidx.**

# HRD-602: Firebase Crashlytics — keep required classes for symbolication.
-keep class com.google.firebase.crashlytics.** { *; }
-keepclassmembers class * {
    @com.google.firebase.crashlytics.ndk.* <methods>;
}
