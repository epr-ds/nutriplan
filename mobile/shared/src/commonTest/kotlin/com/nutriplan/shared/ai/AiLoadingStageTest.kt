package com.nutriplan.shared.ai

import kotlin.test.Test
import kotlin.test.assertEquals

class AiLoadingStageTest {

    @Test
    fun `a request just started is started`() {
        assertEquals(AiLoadingStage.STARTED, AiLoadingStage.after(0))
        assertEquals(AiLoadingStage.STARTED, AiLoadingStage.after(AiLoadingStage.SLOW_AFTER_MILLIS - 1))
    }

    @Test
    fun `after a few seconds a request is slow`() {
        assertEquals(AiLoadingStage.SLOW, AiLoadingStage.after(AiLoadingStage.SLOW_AFTER_MILLIS))
        assertEquals(AiLoadingStage.SLOW, AiLoadingStage.after(AiLoadingStage.VERY_SLOW_AFTER_MILLIS - 1))
    }

    @Test
    fun `after longer a request is very slow`() {
        assertEquals(AiLoadingStage.VERY_SLOW, AiLoadingStage.after(AiLoadingStage.VERY_SLOW_AFTER_MILLIS))
        assertEquals(AiLoadingStage.VERY_SLOW, AiLoadingStage.after(60_000))
    }
}
