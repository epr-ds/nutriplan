package com.nutriplan.shared.contract

/**
 * A minimal, machine-checkable projection of `contracts/identity.openapi.yaml`.
 *
 * This is the "spec-derived mock" the KMP client is exercised against: it enumerates the
 * documented operations and the request/response schemas the client must speak. It mirrors
 * the OpenAPI document, and `scripts/check_mobile_identity_contract.py` parses both the spec
 * and the client models and fails CI if either drifts from the other.
 */
internal object IdentityContract {

    /** The gateway route + API version prefix that fronts the identity service. */
    const val clientPrefix: String = "/identity/v1"

    /** A documented operation: method + service-relative path and its body schemas. */
    data class Operation(
        val method: String,
        val path: String,
        val requestSchema: String?,
        val responseSchema: String,
        val successStatus: Int,
    )

    /** A schema's required and allowed property names (camelCase, as on the wire). */
    data class Schema(
        val required: Set<String>,
        val properties: Set<String>,
    )

    val operations: List<Operation> = listOf(
        Operation("POST", "/auth/register", "RegisterRequest", "AuthResponse", 201),
        Operation("POST", "/auth/login", "LoginRequest", "AuthResponse", 200),
        Operation("POST", "/auth/oauth/{provider}", "OAuthRequest", "AuthResponse", 200),
        Operation("POST", "/auth/refresh", "RefreshRequest", "AuthResponse", 200),
        Operation("GET", "/users/me", null, "UserProfileResponse", 200),
        Operation("PUT", "/users/me", "UpdateProfileRequest", "UserProfileResponse", 200),
        Operation(
            "PUT",
            "/users/me/dietary-preferences",
            "DietaryPreferencesRequest",
            "DietaryPreferencesRequest",
            200,
        ),
        Operation(
            "POST",
            "/users/me/avatar-upload-url",
            "AvatarUploadRequest",
            "AvatarUploadResponse",
            200,
        ),
        Operation("PUT", "/users/me/avatar", "AvatarConfirmRequest", "UserProfileResponse", 200),
    )

    val schemas: Map<String, Schema> = mapOf(
        "RegisterRequest" to Schema(
            required = setOf("email", "password", "name"),
            properties = setOf("email", "password", "name"),
        ),
        "LoginRequest" to Schema(
            required = setOf("email", "password"),
            properties = setOf("email", "password"),
        ),
        "OAuthRequest" to Schema(
            required = setOf("idToken"),
            properties = setOf("idToken", "nonce"),
        ),
        "RefreshRequest" to Schema(
            required = setOf("refreshToken"),
            properties = setOf("refreshToken"),
        ),
        "AuthResponse" to Schema(
            required = setOf("accessToken", "refreshToken", "expiresIn", "user"),
            properties = setOf("accessToken", "refreshToken", "expiresIn", "user"),
        ),
        "UpdateProfileRequest" to Schema(
            required = emptySet(),
            properties = setOf("name", "avatarUrl"),
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
                "appetiteSatisfactionLevel",
            ),
        ),
        "AvatarUploadRequest" to Schema(
            required = setOf("contentType"),
            properties = setOf("contentType"),
        ),
        "AvatarUploadResponse" to Schema(
            required = setOf("uploadUrl", "key", "expiresIn", "requiredHeaders"),
            properties = setOf("uploadUrl", "key", "expiresIn", "requiredHeaders"),
        ),
        "AvatarConfirmRequest" to Schema(
            required = setOf("key"),
            properties = setOf("key"),
        ),
        "UserProfileResponse" to Schema(
            required = setOf("id", "email", "name", "avatarUrl", "dietaryPreferences", "createdAt"),
            properties = setOf("id", "email", "name", "avatarUrl", "dietaryPreferences", "createdAt"),
        ),
    )
}
