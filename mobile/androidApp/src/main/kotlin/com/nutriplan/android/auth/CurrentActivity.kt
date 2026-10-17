package com.nutriplan.android.auth

import android.app.Activity
import java.lang.ref.WeakReference

/**
 * Holds a weak reference to the current [Activity] so components outside the Compose layer (the
 * Credential Manager OAuth flow) can launch native UI. Set from `MainActivity.onCreate`.
 */
object CurrentActivity {

    @Volatile
    private var reference: WeakReference<Activity>? = null

    fun set(activity: Activity) {
        reference = WeakReference(activity)
    }

    fun get(): Activity? = reference?.get()
}
