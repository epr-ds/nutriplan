package com.nutriplan.shared.integration

import com.nutriplan.shared.ai.AiAdvisor
import com.nutriplan.shared.ai.AiResult
import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.ApiEnvironment
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AiRepositoryImpl
import com.nutriplan.shared.data.repository.CommerceRepositoryImpl
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.data.repository.IdentityRepositoryImpl
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * True client↔backend integration test (mobile): the full backend journey behind the AI's meal
 * recommendation → plan → order flow.
 *
 * The journey runs through the real Ktor HTTP client (OkHttp engine) against a real backend HTTP
 * server ([StubBackendServer]) — the same client code paths a device takes — and covers the backend
 * edges the journey crosses: register → login → dietary preferences → AI recommendation → meal plan
 * add → commerce order placement, each with the bearer token the auth state owns.
 *
 * The AI step answers the versioned gateway recommendation envelope (see the AI backend integration
 * test); the stub answers the shape the contract defines, so a regression in the client's URL
 * construction or response parsing fails here instead of only in the per-endpoint mocks.
 */
class FullJourneyBackendIntegrationTest {

    private val server = StubBackendServer()
    private val authRepository = InMemoryAuthRepository()
    private lateinit var identityRepository: IdentityRepositoryImpl
    private lateinit var dietaryRepository: DietaryRepositoryImpl
    private lateinit var commerceRepository: CommerceRepositoryImpl
    private lateinit var advisor: AiAdvisor

    @BeforeTest
    fun setUp() {
        server.start()
        ApiConfig.configure(ApiEnvironment.LOCAL)
        ApiConfig.useBaseUrl(server.baseUrl)
        authRepository.updateTokens(STUB_TOKEN, STUB_REFRESH_TOKEN)
        HttpClientProvider.create(OkHttp, authRepository = authRepository)
        identityRepository = IdentityRepositoryImpl()
        dietaryRepository = DietaryRepositoryImpl()
        commerceRepository = CommerceRepositoryImpl()
        advisor = AiAdvisor(AiRepositoryImpl())
    }

    @AfterTest
    fun tearDown() {
        HttpClientProvider.reset()
        ApiConfig.reset()
        server.stop()
    }

    @Test
    fun `the full backend journey from register to order placement succeeds end to end`() = runTest {
        // Auth: register, then log in — both through the real auth endpoints, owning the tokens.
        authRepository.register(
            RegisterRequest(email = JOURNEY_EMAIL, password = JOURNEY_PASSWORD, name = "Journey User"),
        )
        authRepository.login(LoginRequest(email = JOURNEY_EMAIL, password = JOURNEY_PASSWORD))
        assertTrue(authRepository.isAuthenticated, "the session should be live after login")

        // Preferences: persist the signed-in user's dietary preferences.
        identityRepository.updateDietaryPreferences(
            UpdateDietaryPreferencesRequest(
                dietType = "vegan",
                allergies = listOf("Peanuts"),
                dailyCalorieTarget = 2000,
            ),
        )

        // AI: get tonight's recommendation through the versioned gateway path.
        val outcome = advisor.recommend(preferences = DIETARY_PREFERENCES, mealType = "dinner")
        val recommendations = (outcome as AiResult.Success<AiRecommendations>).value.recommendations
        val picked = recommendations.single()
        assertEquals("Lentil Curry", picked.name)

        // Meal plan: create a plan and add the recommended meal to it.
        val plan: MealPlan = dietaryRepository.createMealPlan(
            CreateMealPlanRequest(
                name = "Week 46",
                startDate = "2026-11-02",
                endDate = "2026-11-08",
                dailyCalorieTarget = 2000,
            ),
        )
        val added = dietaryRepository.addMeal(
            planId = plan.id,
            request = AddMealRequest(mealType = "dinner", recipeId = picked.id, servings = 2.0),
        )
        assertEquals(picked.id, added.recipe?.id)

        // Commerce: place the order for the plan that holds the recommended meal.
        val order: Order = commerceRepository.createOrder(
            request = CreateOrderRequest(
                mealPlanId = plan.id,
                fulfillmentType = "dark_kitchen",
                deliveryAddress = OrderAddress(
                    street = "Av. Reforma 12",
                    city = "Ciudad de Mexico",
                    state = "CDMX",
                    zipCode = "06600",
                    country = "MX",
                ),
                deliveryDate = "2026-11-06",
                deliveryTimeSlot = "13:00-15:00",
            ),
        )
        assertEquals("order-journey-1", order.id)
        assertEquals("pending", order.status)

        // The recorded chain is the journey, in order: auth → preferences → AI → plan → commerce.
        val recorded = server.received.map { "${it.method} ${it.path}" }
        assertEquals(
            listOf(
                "POST /identity/v1/auth/register",
                "POST /identity/v1/auth/login",
                "PUT /identity/v1/users/me/dietary-preferences",
                "POST /ai/v1/recommendations",
                "POST /dietary/v1/meal-plans",
                "POST /dietary/v1/meal-plans/plan-journey-1/meals",
                "POST /commerce/v1/orders",
            ),
            recorded,
        )
    }

    private companion object {
        const val STUB_TOKEN = "integration-test-token"
        const val STUB_REFRESH_TOKEN = "integration-test-refresh-token"

        val JOURNEY_EMAIL = "journey-nutriplan@example.com"
        val JOURNEY_PASSWORD = "JourneyPass1!"

        val DIETARY_PREFERENCES = DietaryPreferences(
            dietType = "vegan",
            allergies = listOf("Peanuts"),
            dailyCalorieTarget = 2000,
        )
    }
}