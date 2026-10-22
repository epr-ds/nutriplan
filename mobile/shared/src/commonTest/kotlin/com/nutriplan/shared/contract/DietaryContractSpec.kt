package com.nutriplan.shared.contract

/**
 * A minimal, machine-checkable projection of `contracts/dietary.openapi.yaml` (DPL-703).
 *
 * This is what the spec-derived mock ([SpecDerivedDietaryMock]) serves: every documented Dietary
 * operation the app's client can call, with its request/response schemas, success status and query
 * parameters. `scripts/check_mobile_dietary_contract.py` parses this file, the OpenAPI document and
 * the client models, and fails CI if any of the three drifts from the others.
 *
 * The AI operations (paths under `/ai/`) in the same document are served by the AI service and consumed by the AI
 * client; they are covered by their own consumer contract tests (AIA-703), not here.
 */
internal object DietaryContract {

    /** The gateway route + API version prefix that fronts the Dietary service. */
    const val clientPrefix: String = "/dietary/v1"

    /**
     * A documented operation: method + service-relative path, the schemas of its body and of its
     * success response ([list] when the response is an array of [response]), and its query
     * parameters.
     */
    data class Operation(
        val method: String,
        val path: String,
        val request: String?,
        val response: String?,
        val status: Int,
        val list: Boolean = false,
        val query: Set<String> = emptySet(),
    )

    /** A schema's required and allowed property names (camelCase, as on the wire). */
    data class Schema(
        val required: Set<String>,
        val properties: Set<String>,
    )

    val operations: List<Operation> = listOf(
        Operation("POST", "/meal-plans", request = "CreateMealPlanRequest", response = "MealPlanResponse", status = 201),
        Operation(
            "GET",
            "/meal-plans",
            request = null,
            response = "MealPlanSummaryResponse",
            status = 200,
            list = true,
            query = setOf("status", "page", "limit"),
        ),
        Operation("GET", "/meal-plans/{planId}", request = null, response = "MealPlanResponse", status = 200),
        Operation(
            "PATCH",
            "/meal-plans/{planId}",
            request = "UpdateMealPlanStatusRequest",
            response = "MealPlanResponse",
            status = 200,
        ),
        Operation("POST", "/meal-plans/{planId}/meals", request = "AddMealRequest", response = "MealResponse", status = 201),
        Operation(
            "PATCH",
            "/meal-plans/{planId}/meals/{mealId}",
            request = "UpdateMealRequest",
            response = "MealResponse",
            status = 200,
        ),
        Operation("DELETE", "/meal-plans/{planId}/meals/{mealId}", request = null, response = null, status = 204),
        Operation(
            "GET",
            "/recipes",
            request = null,
            response = "RecipeResponse",
            status = 200,
            list = true,
            query = setOf("ingredients", "dietType", "maxCalories", "minProtein", "page", "limit"),
        ),
        Operation("GET", "/recipes/{recipeId}", request = null, response = "RecipeResponse", status = 200),
        Operation(
            "GET",
            "/favorites",
            request = null,
            response = "RecipeResponse",
            status = 200,
            list = true,
            query = setOf("page", "limit"),
        ),
        Operation("PUT", "/favorites/{recipeId}", request = null, response = null, status = 204),
        Operation("DELETE", "/favorites/{recipeId}", request = null, response = null, status = 204),
        Operation(
            "GET",
            "/nutrition/disclaimer",
            request = null,
            response = "NutritionDisclaimerResponse",
            status = 200,
        ),
    )

    val schemas: Map<String, Schema> = mapOf(
        "CreateMealPlanRequest" to Schema(
            required = setOf("name", "startDate", "endDate", "dailyCalorieTarget"),
            properties = setOf("name", "startDate", "endDate", "dailyCalorieTarget", "macroTargets", "dietaryType"),
        ),
        "AddMealRequest" to Schema(
            required = setOf("mealType", "recipeId", "servings"),
            properties = setOf("mealType", "recipeId", "servings"),
        ),
        "UpdateMealRequest" to Schema(
            required = emptySet(),
            properties = setOf("servings", "dayIndex", "satisfactionLevel"),
        ),
        "UpdateMealPlanStatusRequest" to Schema(
            required = setOf("status"),
            properties = setOf("status"),
        ),
        "MealPlanSummaryResponse" to Schema(
            required = setOf("id", "name", "startDate", "endDate", "status"),
            properties = setOf("id", "name", "startDate", "endDate", "status"),
        ),
        "MealPlanResponse" to Schema(
            required = setOf("id", "name", "startDate", "endDate", "dailyCalorieTarget", "status", "meals", "nutritionalSummary"),
            properties = setOf("id", "name", "startDate", "endDate", "dailyCalorieTarget", "status", "meals", "nutritionalSummary"),
        ),
        "MealResponse" to Schema(
            required = setOf("id", "mealType", "servings"),
            properties = setOf("id", "mealType", "recipe", "servings", "dayIndex", "satisfactionLevel", "nutritionalInfo"),
        ),
        "RecipeResponse" to Schema(
            required = setOf("id", "name", "servings", "ingredients", "instructions", "dietaryTypes"),
            properties = setOf(
                "id",
                "name",
                "description",
                "ingredients",
                "instructions",
                "prepTime",
                "cookTime",
                "servings",
                "imageUrl",
                "nutritionalInfo",
                "dietaryTypes",
            ),
        ),
        "NutritionDisclaimerResponse" to Schema(
            required = setOf("disclaimer", "medicalAdvice", "sources", "fieldSources", "lastReviewed"),
            properties = setOf("disclaimer", "medicalAdvice", "sources", "fieldSources", "lastReviewed"),
        ),
    )
}
