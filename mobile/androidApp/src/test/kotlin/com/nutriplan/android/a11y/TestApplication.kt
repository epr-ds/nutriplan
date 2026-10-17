package com.nutriplan.android.a11y

import android.app.Application

/**
 * No-op [Application] for the accessibility tests: the production `NutriPlanApplication` starts
 * Koin, and the global Koin context would already be started for the next Robolectric test.
 */
class TestApplication : Application()
