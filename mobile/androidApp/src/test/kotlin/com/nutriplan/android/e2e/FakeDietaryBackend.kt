package com.nutriplan.android.e2e

import com.nutriplan.shared.planning.IsoDate
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlin.math.floor

/**
 * A small, stateful stand-in for the Dietary service for the planning journey (DPL-704): it keeps
 * the plans it is given and computes each plan's nutrition the way the service does (meal nutrition
 * is the recipe's per-serving values times the servings; the plan's daily average is the total over
 * the plan's days; progress compares that average with the plan's targets: under 100% is under,
 * exactly 100% on target, above it over). Responses follow `contracts/dietary.openapi.yaml`.
 *
 * The app module cannot see the shared module's test sources, so this is a copy of the stand-in the
 * shared `PlanningJourneyTest` uses; keep the two in step.
 */
class FakeDietaryBackend(
    recipes: List<CatalogRecipe>,
    /** When given, AI Advisor requests are answered by it (AIA-705); the app uses one HTTP client. */
    private val ai: FakeAiAdvisor? = null,
) {

    /** A catalog recipe with its per-serving nutrition. */
    data class CatalogRecipe(
        val id: String,
        val name: String,
        val calories: Int,
        val protein: Double,
        val carbs: Double,
        val fat: Double,
        val sugar: Double,
        val ingredients: List<String> = listOf(name),
        val dietaryTypes: List<String> = listOf("omnivore"),
    )

    private class Meal(val id: String, val mealType: String, val recipe: CatalogRecipe, val servings: Double) {
        var dayIndex: Int? = null
    }

    private class Plan(
        val id: String,
        val name: String,
        val startDate: String,
        val endDate: String,
        val dailyCalorieTarget: Int,
        val macroTargets: Map<String, Int?>,
    ) {
        val meals = mutableListOf<Meal>()
    }

    private val catalog = recipes.associateBy { it.id }
    private val plans = linkedMapOf<String, Plan>()
    private var nextId = 1
    private val json = Json { ignoreUnknownKeys = true }
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    /** Every request as "METHOD /path" (without the gateway prefix), in order. */
    val requests: MutableList<String> = mutableListOf()

    val engine: MockEngine = MockEngine { request -> handle(request) }

    private fun MockRequestHandleScope.handle(request: HttpRequestData): HttpResponseData {
        if (ai != null && ai.handles(request.url.encodedPath)) {
            requests += "${request.method.value} ${request.url.encodedPath}"
            return with(ai) { handle(request, ::recipeJson) }
        }
        val path = request.url.encodedPath.removePrefix(PREFIX)
        val method = request.method.value
        requests += "$method $path"
        val parts = path.trim('/').split('/')
        val body = (request.body as? TextContent)?.text?.let { json.parseToJsonElement(it).jsonObject }

        return when {
            method == "POST" && parts == listOf("meal-plans") -> created(createPlan(body!!))
            method == "GET" && parts == listOf("meal-plans") -> ok(JsonArray(plans.values.map(::summaryJson)))
            method == "GET" && parts.size == 2 && parts[0] == "meal-plans" ->
                plans[parts[1]]?.let { ok(planJson(it)) } ?: notFound()
            method == "POST" && parts.size == 3 && parts[0] == "meal-plans" && parts[2] == "meals" ->
                plans[parts[1]]?.let { plan -> addMeal(plan, body!!) } ?: notFound()
            method == "PATCH" && parts.size == 4 && parts[2] == "meals" ->
                plans[parts[1]]?.meals?.firstOrNull { it.id == parts[3] }?.let { meal ->
                    body!!["dayIndex"]?.jsonPrimitive?.intOrNull?.let { meal.dayIndex = it }
                    ok(mealJson(meal, withRecipe = false))
                } ?: notFound()
            method == "GET" && parts == listOf("recipes") -> ok(JsonArray(catalog.values.map(::recipeJson)))
            method == "GET" && parts.size == 2 && parts[0] == "recipes" ->
                catalog[parts[1]]?.let { ok(recipeJson(it)) } ?: notFound()
            method == "GET" && parts == listOf("favorites") -> ok(JsonArray(emptyList()))
            method == "GET" && parts == listOf("nutrition", "disclaimer") -> ok(DISCLAIMER)
            else -> notFound()
        }
    }

    private fun createPlan(body: JsonObject): Plan {
        val macros = (body["macroTargets"] as? JsonObject).orEmptyObject()
        val plan = Plan(
            id = "plan-${nextId++}",
            name = body.string("name"),
            startDate = body.string("startDate"),
            endDate = body.string("endDate"),
            dailyCalorieTarget = body["dailyCalorieTarget"]!!.jsonPrimitive.intOrNull!!,
            macroTargets = MACROS.associateWith { macros["${it}Grams"]?.jsonPrimitive?.intOrNull },
        )
        plans[plan.id] = plan
        return plan
    }

    private fun MockRequestHandleScope.addMeal(plan: Plan, body: JsonObject): HttpResponseData {
        val recipe = catalog[body.string("recipeId")]
            ?: return respond(PROBLEM_422, HttpStatusCode.UnprocessableEntity, jsonHeaders)
        val meal = Meal(
            id = "meal-${nextId++}",
            mealType = body.string("mealType"),
            recipe = recipe,
            servings = body["servings"]!!.jsonPrimitive.doubleOrNull!!,
        )
        plan.meals += meal
        return respond(mealJson(meal, withRecipe = true).toString(), HttpStatusCode.Created, jsonHeaders)
    }

    /** The recipes of the meals in the plan [planId], in the order they were added. */
    fun mealRecipes(planId: String): List<CatalogRecipe> = plans[planId]?.meals?.map { it.recipe }.orEmpty()

    // --- nutrition, the way the service computes it ---

    private fun mealNutrition(meal: Meal) = mapOf(
        "calories" to roundInt(meal.recipe.calories * meal.servings).toDouble(),
        "protein" to round1(meal.recipe.protein * meal.servings),
        "carbs" to round1(meal.recipe.carbs * meal.servings),
        "fat" to round1(meal.recipe.fat * meal.servings),
        "sugar" to round1(meal.recipe.sugar * meal.servings),
    )

    private fun summaryOf(plan: Plan): JsonObject {
        val days = (IsoDate.daysBetween(plan.startDate, plan.endDate) ?: 0) + 1
        val total = NUTRIENTS.associateWith { n -> plan.meals.sumOf { mealNutrition(it).getValue(n) } }
        val average = total.mapValues { (n, value) -> if (n == "calories") roundInt(value / days).toDouble() else round1(value / days) }
        val targets = mapOf("calories" to plan.dailyCalorieTarget) + plan.macroTargets
        return buildJsonObject {
            put("total", nutritionJson(total.mapValues { (n, v) -> if (n == "calories") roundInt(v).toDouble() else round1(v) }))
            put("dailyAverage", nutritionJson(average))
            put("targets", JsonObject(NUTRIENTS.associateWith { n -> JsonPrimitive(targets[n]) }))
            put(
                "progress",
                JsonObject(
                    NUTRIENTS.associateWith { n ->
                        val target = targets[n]?.toDouble()
                        val actual = average.getValue(n)
                        val percent = target?.takeIf { it > 0 }?.let { round1(actual / it * 100) }
                        buildJsonObject {
                            put("target", target)
                            put("actual", actual)
                            put("percentOfTarget", percent)
                            put(
                                "status",
                                when {
                                    target == null || target <= 0 -> null
                                    actual < target -> "under"
                                    actual > target -> "over"
                                    else -> "on_target"
                                },
                            )
                        }
                    },
                ),
            )
        }
    }

    // --- JSON shapes (contracts/dietary.openapi.yaml) ---

    private fun summaryJson(plan: Plan) = buildJsonObject {
        put("id", plan.id)
        put("name", plan.name)
        put("startDate", plan.startDate)
        put("endDate", plan.endDate)
        put("status", "draft")
    }

    private fun planJson(plan: Plan) = buildJsonObject {
        summaryJson(plan).forEach { (key, value) -> put(key, value) }
        put("dailyCalorieTarget", plan.dailyCalorieTarget)
        put("meals", JsonArray(plan.meals.map { mealJson(it, withRecipe = false) }))
        put("nutritionalSummary", summaryOf(plan))
    }

    private fun mealJson(meal: Meal, withRecipe: Boolean) = buildJsonObject {
        put("id", meal.id)
        put("mealType", meal.mealType)
        // Plan reads do not expand the recipe; only the add-meal response embeds it.
        put("recipe", if (withRecipe) recipeJson(meal.recipe) else JsonNull)
        put("servings", meal.servings)
        put("dayIndex", meal.dayIndex)
        put("satisfactionLevel", JsonNull)
        put("nutritionalInfo", nutritionJson(mealNutrition(meal)))
    }

    fun recipeJson(recipe: CatalogRecipe): JsonObject = buildJsonObject {
        put("id", recipe.id)
        put("name", recipe.name)
        put("ingredients", JsonArray(recipe.ingredients.map { buildJsonObject { put("name", it) } }))
        put("instructions", JsonArray(listOf(JsonPrimitive("Prepare and serve."))))
        put("servings", 1)
        put(
            "nutritionalInfo",
            nutritionJson(
                mapOf(
                    "calories" to recipe.calories.toDouble(),
                    "protein" to recipe.protein,
                    "carbs" to recipe.carbs,
                    "fat" to recipe.fat,
                    "sugar" to recipe.sugar,
                ),
            ),
        )
        put("dietaryTypes", JsonArray(recipe.dietaryTypes.map { JsonPrimitive(it) }))
    }

    private fun nutritionJson(values: Map<String, Double>): JsonObject = buildJsonObject {
        values.forEach { (n, v) -> if (n == "calories") put(n, roundInt(v)) else put(n, v) }
    }

    private fun MockRequestHandleScope.ok(body: JsonElement) = respond(body.toString(), HttpStatusCode.OK, jsonHeaders)

    private fun MockRequestHandleScope.created(plan: Plan) =
        respond(planJson(plan).toString(), HttpStatusCode.Created, jsonHeaders)

    private fun MockRequestHandleScope.notFound() = respond(PROBLEM_404, HttpStatusCode.NotFound, jsonHeaders)

    private fun JsonObject.string(key: String): String = getValue(key).jsonPrimitive.content

    private fun JsonObject?.orEmptyObject(): JsonObject = this ?: JsonObject(emptyMap())

    private companion object {
        const val PREFIX = "/dietary/v1"
        val NUTRIENTS = listOf("calories", "protein", "carbs", "fat", "sugar")
        val MACROS = listOf("protein", "carbs", "fat", "sugar")
        const val PROBLEM_404 = """{"type":"about:blank","title":"Not Found","status":404}"""
        const val PROBLEM_422 = """{"type":"about:blank","title":"Unprocessable Entity","status":422}"""
        val DISCLAIMER: JsonElement = Json.parseToJsonElement(
            """{"disclaimer":"Estimates only.","medicalAdvice":false,"sources":[],""" +
                """"fieldSources":{"calories":"x","protein":"x","carbs":"x","fat":"x","sugar":"x"},""" +
                """"lastReviewed":"2026-09-01"}""",
        )

        /** Half-up rounding to a whole number, like the service. */
        fun roundInt(value: Double): Int = floor(value + 0.5).toInt()

        /** Half-up rounding to one decimal. */
        fun round1(value: Double): Double = floor(value * 10 + 0.5) / 10
    }
}
