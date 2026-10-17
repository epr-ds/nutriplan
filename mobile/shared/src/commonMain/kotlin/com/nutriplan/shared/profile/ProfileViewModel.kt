package com.nutriplan.shared.profile

import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.model.UpdateProfileRequest
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.IdentityRepository
import com.nutriplan.shared.session.SessionManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the profile screen and its editors.
 *
 * [isSaved] is a transient success flag the UI can use to confirm a save (e.g. pop back) and then
 * clear with [ProfileViewModel.consumeSaved].
 */
data class ProfileUiState(
    val profile: UserProfile? = null,
    val isLoading: Boolean = false,
    val loadError: String? = null,
    val isSaving: Boolean = false,
    val saveError: String? = null,
    val isSaved: Boolean = false,
) {
    val hasProfile: Boolean get() = profile != null
}

/**
 * Shared profile logic used by the Compose (IDN-606) and SwiftUI screens: view and edit the name,
 * avatar, and dietary preferences.
 *
 * Every successful mutation goes through [apply], which updates the local [ProfileUiState] and
 * tells the [SessionManager] about the new profile, so a change reflects everywhere immediately
 * (navigation, other screens) rather than only on the next load.
 */
class ProfileViewModel(
    private val identityRepository: IdentityRepository,
    private val sessionManager: SessionManager,
) {

    private val _state = MutableStateFlow(ProfileUiState())
    val state: StateFlow<ProfileUiState> = _state.asStateFlow()

    /** Load (or refresh) the current profile. */
    suspend fun load(): Boolean {
        _state.update { it.copy(isLoading = true, loadError = null) }
        return try {
            apply(identityRepository.getMe(), saved = false)
            _state.update { it.copy(isLoading = false, loadError = null) }
            true
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoading = false, loadError = e.toProfileErrorMessage()) }
            false
        }
    }

    /** Save a new display name. Empty names are rejected inline without a request. */
    suspend fun saveName(name: String): Boolean {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) {
            _state.update { it.copy(saveError = "Enter your name.") }
            return false
        }
        return save { identityRepository.updateMe(UpdateProfileRequest(name = trimmed)) }
    }

    /** Save dietary preferences and refresh the profile. */
    suspend fun savePreferences(request: UpdateDietaryPreferencesRequest): Boolean = save {
        identityRepository.updateDietaryPreferences(request)
        identityRepository.getMe()
    }

    /** Upload a new avatar image and refresh the profile. */
    suspend fun updateAvatar(contentType: String, bytes: ByteArray): Boolean =
        save { identityRepository.updateAvatar(contentType, bytes) }

    /** Clear the transient success flag once the UI has reacted to it. */
    fun consumeSaved() {
        _state.update { it.copy(isSaved = false) }
    }

    private suspend fun save(block: suspend () -> UserProfile): Boolean {
        _state.update { it.copy(isSaving = true, saveError = null, isSaved = false) }
        return try {
            apply(block(), saved = true)
            _state.update { it.copy(isSaving = false, isSaved = true, saveError = null) }
            true
        } catch (e: CancellationException) {
            _state.update { it.copy(isSaving = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isSaving = false, saveError = e.toProfileErrorMessage()) }
            false
        }
    }

    private fun apply(user: UserProfile, saved: Boolean) {
        _state.update { it.copy(profile = user, isSaved = saved) }
        // Reflect the change everywhere immediately by refreshing the session's copy of the user.
        sessionManager.onAuthenticated(user)
    }

    private fun Throwable.toProfileErrorMessage(): String = when (this) {
        is ApiException.NetworkError -> "Can't reach the server. Check your connection and try again."
        is ApiException.HttpError ->
            if (statusCode in 500..599) {
                "The server had a problem. Please try again later."
            } else {
                "We couldn't save your changes. Please try again."
            }
        else -> "Something went wrong. Please try again."
    }
}
