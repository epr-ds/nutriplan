package com.nutriplan.shared.contract

/**
 * A minimal, machine-checkable projection of `contracts/ai.openapi.yaml` (AIA-703).
 *
 * This is what the spec-derived mock ([SpecDerivedAiMock]) serves: the AI Advisor operations the
 * app's client calls, with their request/response schemas and success status, and the allowed values
 * of the request fields that are enums (and of the response enums the app branches on). `scripts/check_mobile_ai_contract.py` parses this file, the
 * OpenAPI document and the client models, and fails CI if any of the three drifts from the others.
 *
 * The health probes in the same document are for the platform, not the app, so they are left out.
 */
internal object AiContract {

    /** The gateway route + API version prefix that fronts the AI service. */
    const val clientPrefix: String = "/ai/v1"

    /** A documented operation: method + service-relative path, body and response schemas, status. */
    data class Operation(
        val method: String,
        val path: String,
        val request: String?,
        val response: String?,
        val status: Int,
    )

    /**
     * A schema's required and allowed property names (camelCase, as on the wire), the allowed values
     * of its enum properties, and the schema of its nested object properties.
     */
    data class Schema(
        val required: Set<String>,
        val properties: Set<String>,
        val enums: Map<String, Set<String>> = emptyMap(),
        val nested: Map<String, String> = emptyMap(),
    )

    val operations: List<Operation> = listOf(
        Operation(
            "POST",
            "/ai/recommendations",
            request = "AIRecommendationRequest",
            response = "AIRecommendationResponse",
            status = 200,
        ),
        Operation(
            "POST",
            "/ai/analyze-meal",
            request = "AnalyzeMealRequest",
            response = "NutritionalAnalysisResponse",
            status = 200,
        ),
        Operation("POST", "/ai/optimize-plan", request = "OptimizePlanRequest", response = "MealPlanResponse", status = 200),
    )

    val schemas: Map<String, Schema> = mapOf(
        "AIRecommendationRequest" to Schema(
            required = setOf("context"),
            properties = setOf(
                "context",
                "dietaryPreferences",
                "availableIngredients",
                "mealType",
                "calorieTarget",
                "previousMeals",
                "constraints",
                "language",
            ),
            enums = mapOf(
                "context" to setOf("meal_plan", "single_meal", "ingredient_based"),
                "mealType" to setOf("breakfast", "lunch", "dinner", "snack"),
                "language" to setOf("es", "en"),
            ),
            nested = mapOf("dietaryPreferences" to "DietaryPreferencesRequest"),
        ),
        "DietaryPreferencesRequest" to Schema(
            required = emptySet(),
            properties = setOf(
                "dietType",
                "allergies",
                "dailyCalorieTarget",
                "macroTargets",
                "excludedIngredients",
                "cuisinePreferences",
            ),
            enums = mapOf("dietType" to setOf("omnivore", "vegetarian", "vegan", "keto", "paleo", "mediterranean")),
            nested = mapOf("macroTargets" to "MacroTargets"),
        ),
        "MacroTargets" to Schema(
            required = emptySet(),
            properties = setOf("proteinGrams", "carbsGrams", "fatGrams", "sugarGrams"),
        ),
        "AIRecommendationResponse" to Schema(
            required = setOf("recommendations"),
            properties = setOf("recommendations", "reasoning", "nutritionalAlignment", "disclaimer", "source"),
            enums = mapOf("source" to setOf("model", "curated_fallback")),
        ),
        "AnalyzeMealRequest" to Schema(
            required = setOf("description"),
            properties = setOf("description", "ingredients"),
        ),
        "NutritionalAnalysisResponse" to Schema(
            required = setOf("warnings"),
            properties = setOf("nutritionalInfo", "alignment", "warnings", "disclaimer"),
        ),
        "OptimizePlanRequest" to Schema(
            required = setOf("planId"),
            properties = setOf("planId", "goal"),
            enums = mapOf(
                "goal" to setOf("balance_macros", "increase_protein", "reduce_calories", "increase_satisfaction"),
            ),
        ),
        "MealPlanResponse" to Schema(
            required = setOf("id", "name", "startDate", "endDate", "dailyCalorieTarget", "status", "meals"),
            properties = setOf(
                "id",
                "name",
                "startDate",
                "endDate",
                "dailyCalorieTarget",
                "status",
                "meals",
                "nutritionalSummary",
            ),
        ),
    )
}
