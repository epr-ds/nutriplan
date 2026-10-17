package com.nutriplan.shared.profile

import com.nutriplan.shared.data.model.AvatarUploadUrlRequest
import com.nutriplan.shared.data.model.AvatarUploadUrlResponse
import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.model.UpdateProfileRequest
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.repository.IdentityRepository

/** In-memory [IdentityRepository] for profile tests. */
internal class FakeProfileIdentityRepository(
    private var profile: UserProfile,
    private val getError: Throwable? = null,
    private val saveError: Throwable? = null,
) : IdentityRepository {

    var lastProfileRequest: UpdateProfileRequest? = null
        private set
    var lastPreferences: UpdateDietaryPreferencesRequest? = null
        private set
    var lastAvatar: Pair<String, ByteArray>? = null
        private set

    override suspend fun getMe(): UserProfile {
        getError?.let { throw it }
        return profile
    }

    override suspend fun updateMe(request: UpdateProfileRequest): UserProfile {
        saveError?.let { throw it }
        lastProfileRequest = request
        profile = profile.copy(name = request.name ?: profile.name, avatarUrl = request.avatarUrl ?: profile.avatarUrl)
        return profile
    }

    override suspend fun updateDietaryPreferences(request: UpdateDietaryPreferencesRequest) {
        saveError?.let { throw it }
        lastPreferences = request
    }

    override suspend fun getAvatarUploadUrl(request: AvatarUploadUrlRequest): AvatarUploadUrlResponse =
        error("not used")

    override suspend fun setAvatar(key: String) = error("not used")

    override suspend fun updateAvatar(contentType: String, bytes: ByteArray): UserProfile {
        saveError?.let { throw it }
        lastAvatar = contentType to bytes
        profile = profile.copy(avatarUrl = "https://cdn.example.com/avatar.png")
        return profile
    }
}
