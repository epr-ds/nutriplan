package com.nutriplan.shared.contract

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.RecipeSearchQuery
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.data.repository.FavoriteRecipesRemoteImpl
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Consumer contract tests for the KMP Dietary client (DPL-703).
 *
 * The real client classes the app ships ([DietaryRepositoryImpl], [FavoriteRecipesRemoteImpl]) are
 * pointed at [SpecDerivedDietaryMock]. Every call must hit a documented operation with documented
 * query parameters and a schema-shaped body, and the client must read the spec-shaped reply, with
 * every documented field. A drifted client (renamed field, wrong path or parameter, changed type)
 * makes a call fail or gets flagged as a contract violation, which fails CI. The mock itself is kept
 * equal to the OpenAPI document by `scripts/check_mobile_dietary_contract.py`.
 */
class DietaryConsumerContractTest {

    private val mock = SpecDerivedDietaryMock()
    private lateinit var dietary: DietaryRepositoryImpl
    private lateinit var favorites: FavoriteRecipesRemoteImpl

    @BeforeTest
    fun setUp() {
        HttpClientProvider.create(mock.engine, authRepository = null)
        dietary = DietaryRepositoryImpl()
        favorites = FavoriteRecipesRemoteImpl()
    }

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun assertNoViolations() =
        assertTrue(mock.violations.isEmpty(), "contract violations: ${mock.violations}")

    private fun assertCalled(operation: String) =
        assertTrue(operation in mock.calls, "expected $operation, saw ${mock.calls}")

    // --- meal plans ---

    @Test
    fun `creating a plan sends a documented body and reads the full plan`() = runTest {
        val plan = dietary.createMealPlan(
            CreateMealPlanRequest(
                name = "Week 40",
                startDate = "2026-10-01",
                endDate = "2026-10-07",
                dailyCalorieTarget = 2000,
                macroTargets = DietaryMacroTargets(proteinGrams = 150),
                dietaryType = "vegetarian",
            ),
        )

        assertCalled("POST /meal-plans")
        assertEquals("Week 40", plan.name)
        assertEquals(2000, plan.dailyCalorieTarget)
        assertNoViolations()
    }

    @Test
    fun `creating a plan with only the required fields conforms too`() = runTest {
        dietary.createMealPlan(
            CreateMealPlanRequest(name = "Plan", startDate = "2026-10-01", endDate = "2026-10-07", dailyCalorieTarget = 1800),
        )

        assertNoViolations()
    }

    @Test
    fun `listing plans uses the documented query parameters and reads summaries`() = runTest {
        val plans = dietary.getMealPlans(MealPlanQuery(status = "active", page = 2, limit = 10))

        assertCalled("GET /meal-plans")
        assertEquals("Week 40", plans.single().name)
        assertEquals("draft", plans.single().status)
        assertNoViolations()
    }

    @Test
    fun `listing plans without a query conforms`() = runTest {
        dietary.getMealPlans()

        assertNoViolations()
    }

    @Test
    fun `reading a plan decodes its meals and the whole nutrition summary`() = runTest {
        val plan = dietary.getMealPlan("33333333-3333-3333-3333-333333333333")

        assertCalled("GET /meal-plans/{planId}")
        val meal = plan.meals.single()
        assertEquals("breakfast", meal.mealType)
        assertEquals(1.5, meal.servings)
        assertEquals(0, meal.dayIndex)
        assertNull(meal.recipe, "plan reads do not expand the recipe")
        assertEquals(365, meal.nutritionalInfo?.calories)
        val summary = assertNotNull(plan.nutritionalSummary)
        assertEquals(365, summary.total?.calories)
        assertEquals(52, summary.dailyAverage?.calories)
        assertEquals(2000, summary.targets.calories)
        assertEquals(150, summary.targets.protein)
        assertEquals("under", summary.progress.calories.status)
        assertEquals(2.6, summary.progress.calories.percentOfTarget)
        assertNull(summary.progress.carbs.status)
        assertNoViolations()
    }

    @Test
    fun `changing a plan's status sends only the status`() = runTest {
        val plan = dietary.updateMealPlanStatus("33333333-3333-3333-3333-333333333333", "active")

        assertCalled("PATCH /meal-plans/{planId}")
        assertEquals("Week 40", plan.name)
        assertNoViolations()
    }

    // --- meals ---

    @Test
    fun `adding a meal sends a documented body and reads the embedded recipe`() = runTest {
        val meal = dietary.addMeal(
            "33333333-3333-3333-3333-333333333333",
            AddMealRequest(mealType = "lunch", recipeId = "11111111-1111-1111-1111-111111111111", servings = 1.0),
        )

        assertCalled("POST /meal-plans/{planId}/meals")
        assertEquals("Overnight Oats with Berries", meal.recipe?.name)
        assertEquals("https://images.nutriplan.app/recipes/overnight-oats.jpg", meal.recipe?.imageUrl)
        assertNoViolations()
    }

    @Test
    fun `every kind of partial meal update conforms`() = runTest {
        val planId = "33333333-3333-3333-3333-333333333333"
        val mealId = "22222222-2222-2222-2222-222222222222"

        dietary.updateMeal(planId, mealId, UpdateMealRequest(servings = 2.0))
        dietary.updateMeal(planId, mealId, UpdateMealRequest(dayIndex = 3))
        dietary.updateMeal(planId, mealId, UpdateMealRequest(satisfactionLevel = 5))
        val meal = dietary.updateMeal(planId, mealId, UpdateMealRequest(servings = 1.0, dayIndex = 1, satisfactionLevel = 4))

        assertCalled("PATCH /meal-plans/{planId}/meals/{mealId}")
        assertEquals("lunch", meal.mealType)
        assertNoViolations()
    }

    @Test
    fun `removing a meal conforms and reads the empty 204`() = runTest {
        dietary.removeMeal("33333333-3333-3333-3333-333333333333", "22222222-2222-2222-2222-222222222222")

        assertCalled("DELETE /meal-plans/{planId}/meals/{mealId}")
        assertNoViolations()
    }

    // --- recipes ---

    @Test
    fun `searching recipes with every filter uses only documented parameters`() = runTest {
        val recipes = dietary.searchRecipes(
            RecipeSearchQuery(
                ingredients = listOf("oats", "milk"),
                dietType = "vegetarian",
                maxCalories = 500,
                minProtein = 10.0,
                page = 2,
                limit = 10,
            ),
        )

        assertCalled("GET /recipes")
        val recipe = recipes.single()
        assertEquals("Overnight Oats with Berries", recipe.name)
        assertEquals(listOf("vegetarian", "omnivore"), recipe.dietaryTypes)
        assertEquals(80.0, recipe.ingredients.single().quantity)
        assertEquals(243, recipe.nutritionalInfo?.calories)
        assertNoViolations()
    }

    @Test
    fun `searching recipes without filters conforms`() = runTest {
        dietary.searchRecipes()

        assertNoViolations()
    }

    @Test
    fun `reading a recipe decodes every documented field`() = runTest {
        val recipe = dietary.getRecipe("11111111-1111-1111-1111-111111111111")

        assertCalled("GET /recipes/{recipeId}")
        assertEquals("No-cook oats soaked overnight.", recipe.description)
        assertEquals(listOf("Combine oats and milk.", "Chill overnight."), recipe.instructions)
        assertEquals(5, recipe.prepTime)
        assertEquals(0, recipe.cookTime)
        assertEquals(2, recipe.servings)
        assertNoViolations()
    }

    @Test
    fun `reading the nutrition disclaimer conforms`() = runTest {
        val disclaimer = dietary.getNutritionDisclaimer()

        assertCalled("GET /nutrition/disclaimer")
        assertEquals(false, disclaimer.medicalAdvice)
        assertEquals("USDA FoodData Central", disclaimer.sources.single().name)
        assertEquals(true, disclaimer.sources.single().verified)
        assertEquals("2026-09-01", disclaimer.lastReviewed)
        assertNoViolations()
    }

    // --- favorites ---

    @Test
    fun `listing favorites uses the documented paging and reads full recipes`() = runTest {
        val recipes = favorites.list(page = 1, limit = 100)

        assertCalled("GET /favorites")
        assertEquals("Overnight Oats with Berries", recipes.single().name)
        assertNoViolations()
    }

    @Test
    fun `saving and removing a favorite conform and read the empty 204s`() = runTest {
        favorites.add("11111111-1111-1111-1111-111111111111")
        favorites.remove("11111111-1111-1111-1111-111111111111")

        assertCalled("PUT /favorites/{recipeId}")
        assertCalled("DELETE /favorites/{recipeId}")
        assertNoViolations()
    }

    // --- the mock catches drift ---

    @Test
    fun `an undocumented operation is a violation`() = runTest {
        val response = HttpClientProvider.client.get("${DietaryContract.clientPrefix}/meal-plans/p1/shopping-list")

        assertEquals(HttpStatusCode.BadRequest, response.status)
        assertTrue(mock.violations.any { it.contains("undocumented operation") })
    }

    @Test
    fun `an undocumented query parameter is a violation`() = runTest {
        HttpClientProvider.client.get("${DietaryContract.clientPrefix}/recipes") { parameter("offset", 20) }

        assertTrue(mock.violations.any { it.contains("undocumented query parameter") && it.contains("offset") })
    }

    @Test
    fun `an undocumented body field is a violation`() = runTest {
        HttpClientProvider.client.post("${DietaryContract.clientPrefix}/meal-plans/p1/meals") {
            contentType(ContentType.Application.Json)
            setBody("""{"mealType":"lunch","recipeId":"r1","servings":1,"portion":2}""")
        }

        assertTrue(mock.violations.any { it.contains("undocumented field") && it.contains("portion") })
    }

    @Test
    fun `a missing required body field is a violation`() = runTest {
        HttpClientProvider.client.post("${DietaryContract.clientPrefix}/meal-plans") {
            contentType(ContentType.Application.Json)
            setBody("""{"name":"Plan","startDate":"2026-10-01","endDate":"2026-10-07"}""")
        }

        assertTrue(mock.violations.any { it.contains("missing required") && it.contains("dailyCalorieTarget") })
    }

    @Test
    fun `an empty partial meal update is a violation`() = runTest {
        HttpClientProvider.client.patch("${DietaryContract.clientPrefix}/meal-plans/p1/meals/m1") {
            contentType(ContentType.Application.Json)
            setBody("{}")
        }

        assertTrue(mock.violations.any { it.contains("at least one") })
    }

    @Test
    fun `a request outside the Dietary prefix is a violation`() = runTest {
        HttpClientProvider.client.get("/v1/meal-plans")

        assertTrue(mock.violations.any { it.contains("outside") })
    }

    @Test
    fun `every documented operation is exercised by this suite`() {
        val exercised = setOf(
            "POST /meal-plans", "GET /meal-plans", "GET /meal-plans/{planId}", "PATCH /meal-plans/{planId}",
            "POST /meal-plans/{planId}/meals", "PATCH /meal-plans/{planId}/meals/{mealId}",
            "DELETE /meal-plans/{planId}/meals/{mealId}", "GET /recipes", "GET /recipes/{recipeId}",
            "GET /favorites", "PUT /favorites/{recipeId}", "DELETE /favorites/{recipeId}", "GET /nutrition/disclaimer",
        )

        assertEquals(DietaryContract.operations.map { "${it.method} ${it.path}" }.toSet(), exercised)
    }
}
