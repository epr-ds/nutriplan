package com.nutriplan.shared.domain

/**
 * Generic wrapper for the outcome of a use-case or repository call. Lives in the domain
 * layer so it can be shared across features without leaking data-layer concerns.
 */
sealed interface Resource<out T> {
    data class Success<T>(val data: T) : Resource<T>
    data class Failure(val error: Throwable) : Resource<Nothing>
    data object Loading : Resource<Nothing>
}
