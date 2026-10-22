package com.nutriplan.shared.data.model

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** AIA-601: the AI models read and write exactly the shapes of `contracts/ai.openapi.yaml`. */
class AiModelsTest {

    /** The same settings as the app's HTTP client. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
        isLenient = true
    }

    private fun keys(value: String) = json.parseToJsonElement(value).jsonObject.keys

    // --- requests ---

    @Test
    fun `a minimal recommendation request sends only the context and the language`() {
        val body = json.encodeToString(AiRecommendationRequest.serializer(), AiRecommendationRequest(context = "meal_plan"))

        assertEquals("""{"context":"meal_plan","language":"es"}""", body)
    }

    @Test
    fun `a full recommendation request uses only documented fields`() {
        val body = json.encodeToString(
            AiRecommendationRequest.serializer(),
            AiRecommendationRequest(
                context = "ingredient_based",
                dietaryPreferences = AiDietaryPreferences(
                    dietType = "vegan",
                    allergies = listOf("peanuts"),
                    dailyCalorieTarget = 1800,
                    macroTargets = DietaryMacroTargets(proteinGrams = 120),
                    excludedIngredients = listOf("tofu"),
                    cuisinePreferences = listOf("mexican"),
                ),
                availableIngredients = listOf("rice"),
                mealType = "lunch",
                calorieTarget = 600,
                previousMeals = listOf("Oats"),
                constraints = listOf("quick"),
                language = "en",
            ),
        )

        assertEquals(
            setOf(
                "context", "dietaryPreferences", "availableIngredients", "mealType", "calorieTarget",
                "previousMeals", "constraints", "language",
            ),
            keys(body),
        )
        val preferences = json.parseToJsonElement(body).jsonObject.getValue("dietaryPreferences").jsonObject
        assertEquals(
            setOf("dietType", "allergies", "dailyCalorieTarget", "macroTargets", "excludedIngredients", "cuisinePreferences"),
            preferences.keys,
        )
    }

    @Test
    fun `unset preference fields are left out not sent as null`() {
        val body = json.encodeToString(AiDietaryPreferences.serializer(), AiDietaryPreferences(dietType = "keto"))

        assertEquals("""{"dietType":"keto"}""", body)
    }

    @Test
    fun `a meal analysis request carries the description and ingredients only when given`() {
        assertEquals(
            """{"description":"Chicken with rice"}""",
            json.encodeToString(AnalyzeMealRequest.serializer(), AnalyzeMealRequest("Chicken with rice")),
        )
        val withIngredients = json.encodeToString(
            AnalyzeMealRequest.serializer(),
            AnalyzeMealRequest("Bowl", ingredients = listOf(RecipeIngredient(name = "Rice", quantity = 100.0, unit = "g"))),
        )
        assertEquals(setOf("description", "ingredients"), keys(withIngredients))
    }

    @Test
    fun `an optimization request sends the goal only when chosen`() {
        assertEquals("""{"planId":"p1"}""", json.encodeToString(OptimizePlanRequest.serializer(), OptimizePlanRequest("p1")))
        assertEquals(
            """{"planId":"p1","goal":"increase_protein"}""",
            json.encodeToString(OptimizePlanRequest.serializer(), OptimizePlanRequest("p1", goal = "increase_protein")),
        )
    }

    // --- responses ---

    @Test
    fun `recommendations decode full catalog recipes with reasoning alignment and disclaimer`() {
        val result = json.decodeFromString(
            AiRecommendations.serializer(),
            """
            {"recommendations":[{"id":"r1","name":"Lentil Soup","description":null,"servings":2,
              "ingredients":[{"name":"Lentils","quantity":200,"unit":"g","calories":230,"protein":18,
                "carbs":40,"fat":1,"sugar":2}],
              "instructions":["Simmer"],"prepTime":10,"cookTime":null,"imageUrl":null,
              "nutritionalInfo":{"calories":320,"protein":19.5,"carbs":41,"fat":3,"sugar":4},
              "dietaryTypes":["vegan","vegetarian"]}],
             "reasoning":"High protein, plant based.",
             "nutritionalAlignment":{"score":87.5,"details":"Close to your protein target."},
             "disclaimer":"Not medical advice."}
            """.trimIndent(),
        )

        val recipe = result.recommendations.single()
        assertEquals("Lentil Soup", recipe.name)
        assertEquals(320, recipe.nutritionalInfo?.calories)
        assertEquals(200.0, recipe.ingredients.single().quantity)
        assertNull(recipe.cookTime)
        assertEquals("High protein, plant based.", result.reasoning)
        assertEquals(87.5, result.nutritionalAlignment?.score)
        assertEquals("Not medical advice.", result.disclaimer)
    }

    @Test
    fun `recommendations decode with only the required field`() {
        val result = json.decodeFromString(AiRecommendations.serializer(), """{"recommendations":[]}""")

        assertTrue(result.recommendations.isEmpty())
        assertNull(result.reasoning)
        assertNull(result.nutritionalAlignment)
        assertNull(result.disclaimer)
        // An older server sends no source: the answer is taken as the model's.
        assertNull(result.source)
        assertFalse(result.isCuratedFallback)
    }

    @Test
    fun `recommendations say when they are the curated fallback`() {
        val fallback = json.decodeFromString(
            AiRecommendations.serializer(),
            """{"recommendations":[],"source":"curated_fallback"}""",
        )
        val model = json.decodeFromString(AiRecommendations.serializer(), """{"recommendations":[],"source":"model"}""")

        assertTrue(fallback.isCuratedFallback)
        assertFalse(model.isCuratedFallback)
    }

    @Test
    fun `a meal analysis decodes nutrition alignment warnings and disclaimer nulls included`() {
        val full = json.decodeFromString(
            MealAnalysis.serializer(),
            """{"nutritionalInfo":{"calories":540,"protein":32.0,"carbs":55.0,"fat":18.0,"sugar":null},
               "alignment":{"score":null,"details":null},"warnings":["High sodium"],"disclaimer":"Estimates only."}""",
        )
        assertEquals(540, full.nutritionalInfo?.calories)
        assertNull(full.nutritionalInfo?.sugar)
        assertNull(full.alignment?.score)
        assertEquals(listOf("High sodium"), full.warnings)

        val minimal = json.decodeFromString(MealAnalysis.serializer(), """{"warnings":[],"nutritionalInfo":null,"alignment":null}""")
        assertNull(minimal.nutritionalInfo)
        assertNull(minimal.alignment)
    }

    @Test
    fun `an optimized plan decodes as a draft plan with or without a summary`() {
        val plan = json.decodeFromString(
            MealPlan.serializer(),
            """{"id":"p1","name":"Week 40 (optimized)","startDate":"2026-10-01","endDate":"2026-10-07",
               "dailyCalorieTarget":2000,"status":"draft",
               "meals":[{"id":"m1","mealType":"lunch","servings":1.5,"recipe":null,
                 "nutritionalInfo":{"calories":500,"protein":30,"carbs":50,"fat":15,"sugar":5}}],
               "nutritionalSummary":{"total":{"calories":500},"dailyAverage":{"calories":71},
                 "targets":{"calories":2000,"protein":150,"carbs":null,"fat":null,"sugar":null}}}""",
        )
        assertEquals("draft", plan.status)
        assertEquals(1.5, plan.meals.single().servings)
        assertEquals(71, plan.nutritionalSummary?.dailyAverage?.calories)
        // The AI contract's summary has no progress; the client's default stands in.
        assertNull(plan.nutritionalSummary?.progress?.calories?.status)

        val bare = json.decodeFromString(
            MealPlan.serializer(),
            """{"id":"p2","name":"Empty","startDate":"2026-10-01","endDate":"2026-10-07","dailyCalorieTarget":1800,
               "status":"draft","meals":[],"nutritionalSummary":null}""",
        )
        assertNull(bare.nutritionalSummary)
    }
}
