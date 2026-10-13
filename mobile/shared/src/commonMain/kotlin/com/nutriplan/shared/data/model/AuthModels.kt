++ b/mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/data/model/AuthModels.kt
package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Request body for registration. */
@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    val firstName: String,
    val lastName: String,
    val dietaryPreferences: List<String>? = null,
)

/** Request body for login. */
@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

/** Request body for token refresh. */
@Serializable
data class RefreshRequest(
    val refreshToken: String,
)

/** Response from auth endpoints (login, register, refresh). */
@Serializable
data class AuthResponse(
    val accessToken: String,
    val refreshToken: String,
    val expiresIn: Long,
)

/** OAuth provider configuration. */
@Serializable
data class OAuthProvider(
    val provider: String,
)

/** User profile returned from identity endpoints. */
@Serializable
data class UserProfile(
    val id: String,
    val email: String,
    val firstName: String,
    val lastName: String,
    val avatarUrl: String? = null,
    val dietaryPreferences: List<String>? = null,
    val createdAt: String? = null,
    val updatedAt: String? = null,
)

/** Request to update user profile. */
@Serializable
data class UpdateProfileRequest(
    val firstName: String? = null,
    val lastName: String? = null,
    val email: String? = null,
)

/** Request to update dietary preferences. */
@Serializable
data class UpdateDietaryPreferencesRequest(
    val preferences: List<String>,
)

/** Request to upload avatar. */
@Serializable
data class AvatarUploadUrlRequest(
    val fileName: String,
    val contentType: String,
)

/** Response with presigned upload URL. */
@Serializable
data class AvatarUploadUrlResponse(
    val uploadUrl: String,
    val avatarUrl: String,
)
