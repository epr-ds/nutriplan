package com.nutriplan.shared

import kotlin.test.Test
import kotlin.test.assertTrue

class GreetingTest {
    @Test
    fun greeting_contains_app_name() {
        assertTrue(Greeting().greet().contains("NutriPlan"))
    }
}
