package com.nutriplan.shared.e2e

import com.nutriplan.shared.ai.AiAdvisor
import com.nutriplan.shared.ai.AiRecommendationsViewModel
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AiRepositoryImpl
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.planning.AddMealViewModel
import com.nutriplan.shared.planning.MealPlanDetailViewModel
import com.nutriplan.shared.planning.Nutrient
import com.nutriplan.shared.planning.ProgressStatus
import com.nutriplan.shared.planning.toNutritionSummaryUi
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * AIA-705: the AI journey through the shared layer: get recommendations → add one to a plan → the
 * added meal respects the user's allergies and calorie target. It runs on the JVM in the Android
 * job and on the iOS simulator in the iOS job, through the same view-models the Compose and SwiftUI
 * screens use, against stand-ins for the Dietary service and the AI Advisor. The AI stand-in's
 * "model" proposes a peanut dish first, and only the service's allergy post-filter removes it, so a
 * safe meal proves the app sent the user's allergies. The Android UI version is `AiJourneyE2ETest`
 * in the app module.
 */
class AiJourneyTest {

    private val peanutNoodles = FakeDietaryBackend.CatalogRecipe(
        "peanut-noodles", "Peanut Noodles", calories = 620, protein = 20.0, carbs = 70.0, fat = 28.0, sugar = 9.0,
        ingredients = listOf("rice noodles", "peanut butter", "lime"),
    )
    private val lentilCurry = FakeDietaryBackend.CatalogRecipe(
        "lentil-curry", "Lentil Curry", calories = 480, protein = 24.0, carbs = 62.0, fat = 12.0, sugar = 8.0,
        ingredients = listOf("red lentils", "coconut milk", "spinach"),
        dietaryTypes = listOf("vegan", "vegetarian"),
    )
    private val catalog = listOf(peanutNoodles, lentilCurry)

    private val ai = FakeAiAdvisor(proposals = catalog)
    private val backend = FakeDietaryBackend(catalog, ai)
    private lateinit var dietary: DietaryRepositoryImpl

    /** The signed-in user's saved preferences. */
    private val preferences = DietaryPreferences(
        dietType = "vegan",
        allergies = listOf("Peanuts"),
        dailyCalorieTarget = 2000,
    )

    @BeforeTest
    fun setUp() {
        HttpClientProvider.create(backend.engine, authRepository = null)
        dietary = DietaryRepositoryImpl()
    }

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    /** A one-week plan (2026-10-01 to 2026-10-07) with the user's 2,000 kcal target. */
    private suspend fun createPlan(): String = dietary.createMealPlan(
        CreateMealPlanRequest(
            name = "Week 40",
            startDate = "2026-10-01",
            endDate = "2026-10-07",
            dailyCalorieTarget = 2000,
        ),
    ).id

    private fun recommendations(preferences: DietaryPreferences?) =
        AiRecommendationsViewModel(AiAdvisor(AiRepositoryImpl()), preferences = { preferences })

    @Test
    fun recommend_add_to_a_plan_and_the_meal_respects_the_allergies_and_the_target() = runTest {
        val planId = createPlan()

        // Recommendations for dinner, for the signed-in user.
        val advisor = recommendations(preferences)
        advisor.onMealTypeChange("dinner")
        advisor.recommend()

        val request = ai.recommendationRequests.single()
        val sentPreferences = assertNotNull(request["dietaryPreferences"]?.jsonObject, "no preferences: $request")
        assertEquals(listOf("Peanuts"), sentPreferences["allergies"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertEquals("vegan", sentPreferences["dietType"]!!.jsonPrimitive.content)
        assertEquals("dinner", request["mealType"]!!.jsonPrimitive.content)
        assertEquals(2000, request["calorieTarget"]!!.jsonPrimitive.content.toInt())

        val state = advisor.state.value
        val picked = assertNotNull(state.result?.recommendations?.firstOrNull(), "a recipe was recommended: $state")

        // Add the top recommendation to the plan, as the meal it was recommended for.
        val form = AddMealViewModel(dietary)
        form.start(planId, picked.id, mealType = state.resultMealType)
        assertEquals("dinner", form.state.value.mealType, "the meal type comes from the recommendation")
        form.onDayChange(0)
        form.save()
        assertTrue(form.state.value.isDone, "the meal should be added: ${form.state.value}")

        // The meal in the plan is safe for the user and fits the target.
        val added = backend.mealRecipes(planId).single()
        assertEquals("lentil-curry", added.id)
        preferences.allergies.orEmpty().forEach { allergy ->
            assertFalse(added.contains(allergy), "${added.name} contains $allergy: ${added.ingredients}")
        }
        assertTrue("vegan" in added.dietaryTypes, "${added.name} is not vegan: ${added.dietaryTypes}")

        val detail = MealPlanDetailViewModel(dietary)
        detail.load(planId)
        val plan = assertNotNull(detail.state.value.plan)
        assertEquals(listOf("dinner"), plan.meals.map { it.mealType })
        val calories = assertNotNull(plan.nutritionalSummary.toNutritionSummaryUi().row(Nutrient.CALORIES))
        assertEquals(2000.0, calories.target)
        assertNotEquals(ProgressStatus.OVER, calories.status, "the plan goes over the calorie target: $calories")
    }

    /** Control: the stand-in is not lenient. Without the allergy the peanut dish is the top pick. */
    @Test
    fun without_the_saved_allergies_the_unsafe_dish_would_be_recommended_first() = runTest {
        val advisor = recommendations(preferences.copy(allergies = null))
        advisor.recommend()

        val first = advisor.state.value.result?.recommendations?.firstOrNull()
        assertEquals("peanut-noodles", first?.id)
    }

    @Test
    fun excluded_ingredients_are_respected_like_allergies() = runTest {
        val advisor = recommendations(preferences.copy(allergies = null, excludedIngredients = listOf("lentil")))
        advisor.recommend()

        val ids = advisor.state.value.result?.recommendations?.map { it.id }
        assertEquals(listOf("peanut-noodles"), ids)
    }
}
