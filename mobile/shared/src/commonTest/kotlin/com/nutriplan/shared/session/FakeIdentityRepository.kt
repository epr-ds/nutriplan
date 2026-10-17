package com.nutriplan.shared.session

import com.nutriplan.shared.data.model.AvatarUploadUrlRequest
import com.nutriplan.shared.data.model.AvatarUploadUrlResponse
import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.model.UpdateProfileRequest
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.repository.IdentityRepository

/** Minimal [IdentityRepository] for onboarding tests: records the save and returns a profile. */
internal class FakeIdentityRepository(
    private val profile: UserProfile,
    private val putError: Throwable? = null,
    private val getError: Throwable? = null,
) : IdentityRepository {

    var lastPreferences: UpdateDietaryPreferencesRequest? = null
        private set
    var getMeCalls = 0
        private set

    override suspend fun getMe(): UserProfile {
        getMeCalls++
        getError?.let { throw it }
        return profile
    }

    override suspend fun updateMe(request: UpdateProfileRequest): UserProfile = error("not used")

    override suspend fun updateDietaryPreferences(request: UpdateDietaryPreferencesRequest) {
        lastPreferences = request
        putError?.let { throw it }
    }

    override suspend fun getAvatarUploadUrl(
        request: AvatarUploadUrlRequest,
    ): AvatarUploadUrlResponse = error("not used")

    override suspend fun setAvatar(key: String) = error("not used")

    override suspend fun updateAvatar(contentType: String, bytes: ByteArray): UserProfile = error("not used")
}
