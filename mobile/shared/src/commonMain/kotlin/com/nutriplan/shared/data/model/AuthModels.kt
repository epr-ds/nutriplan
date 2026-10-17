package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Request body for registration (`POST /auth/register`). */
@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    val name: String,
)

/** Request body for login (`POST /auth/login`). */
@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

/** Request body for OAuth login (`POST /auth/oauth/{provider}`). */
@Serializable
data class OAuthRequest(
    val idToken: String,
    val nonce: String? = null,
)

/** Request body for token refresh (`POST /auth/refresh`). */
@Serializable
data class RefreshRequest(
    val refreshToken: String,
)

/** Response from auth endpoints (login, register, oauth, refresh). */
@Serializable
data class AuthResponse(
    val accessToken: String,
    val refreshToken: String,
    val expiresIn: Long,
    val user: UserProfile,
)

/** Dietary-preference block embedded in a [UserProfile]. */
@Serializable
data class DietaryPreferences(
    val dietType: String? = null,
    val allergies: List<String>? = null,
    val dailyCalorieTarget: Int? = null,
    val macroTargets: MacroTargets? = null,
    val excludedIngredients: List<String>? = null,
    val cuisinePreferences: List<String>? = null,
    val appetiteSatisfactionLevel: Int? = null,
)

/** Macro targets embedded in [DietaryPreferences]. */
@Serializable
data class MacroTargets(
    val proteinGrams: Int? = null,
    val carbsGrams: Int? = null,
    val fatGrams: Int? = null,
    val sugarGrams: Int? = null,
)

/** User profile returned from identity endpoints (`UserProfileResponse`). */
@Serializable
data class UserProfile(
    val id: String,
    val email: String,
    val name: String,
    val avatarUrl: String? = null,
    val dietaryPreferences: DietaryPreferences? = null,
    val createdAt: String? = null,
)

/** Request to update user profile (`PUT /users/me`). */
@Serializable
data class UpdateProfileRequest(
    val name: String? = null,
    val avatarUrl: String? = null,
)

/** Request to update dietary preferences (`PUT /users/me/dietary-preferences`). */
@Serializable
data class UpdateDietaryPreferencesRequest(
    val dietType: String? = null,
    val allergies: List<String>? = null,
    val dailyCalorieTarget: Int? = null,
    val macroTargets: MacroTargets? = null,
    val excludedIngredients: List<String>? = null,
    val cuisinePreferences: List<String>? = null,
    val appetiteSatisfactionLevel: Int? = null,
)

/** Request to presign an avatar upload (`POST /users/me/avatar-upload-url`). */
@Serializable
data class AvatarUploadUrlRequest(
    val contentType: String,
)

/** Response with the presigned upload target (`AvatarUploadResponse`). */
@Serializable
data class AvatarUploadUrlResponse(
    val uploadUrl: String,
    val key: String,
    val expiresIn: Long,
    val requiredHeaders: Map<String, String>,
)

/** Request to confirm an uploaded avatar (`PUT /users/me/avatar`). */
@Serializable
data class AvatarConfirmRequest(
    val key: String,
)
