package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.put
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.encodeURLPathPart
import io.ktor.http.isSuccess
import io.ktor.serialization.ContentConvertException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException

/**
 * The favorites endpoints of the Dietary API (`/favorites`, DPL-607). Failures are thrown as
 * [ApiException]; use [com.nutriplan.shared.data.network.toApiFailure] to classify them.
 */
interface FavoriteRecipesRemote {

    /** The caller's favorite recipes, most recently saved first (`GET /favorites`); [page] is 1-based. */
    suspend fun list(page: Int = 1, limit: Int = DEFAULT_LIMIT): List<Recipe>

    /** Save a recipe (`PUT /favorites/{recipeId}`). Saving twice succeeds; an unknown recipe is a 404. */
    suspend fun add(recipeId: String)

    /** Remove a recipe (`DELETE /favorites/{recipeId}`). Removing a non-favorite also succeeds. */
    suspend fun remove(recipeId: String)

    companion object {
        /** The API's largest page, so a user's favorites take as few requests as possible. */
        const val DEFAULT_LIMIT = 100
    }
}

class FavoriteRecipesRemoteImpl : FavoriteRecipesRemote {

    private val client = HttpClientProvider.client

    override suspend fun list(page: Int, limit: Int): List<Recipe> =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.DIETARY}/favorites") {
                parameter("page", page)
                parameter("limit", limit)
            }.readOrThrow()
        }

    override suspend fun add(recipeId: String) {
        withContext(Dispatchers.IO) {
            client.put("${ApiConfig.DIETARY}/favorites/${recipeId.encodeURLPathPart()}").requireSuccess()
        }
    }

    override suspend fun remove(recipeId: String) {
        withContext(Dispatchers.IO) {
            client.delete("${ApiConfig.DIETARY}/favorites/${recipeId.encodeURLPathPart()}").requireSuccess()
        }
    }

    /** Any non-2xx becomes an [ApiException.HttpError] carrying the status and the problem body. */
    private suspend fun HttpResponse.requireSuccess() {
        if (!status.isSuccess()) {
            throw ApiException.HttpError(statusCode = status.value, body = bodyAsText())
        }
    }

    private suspend inline fun <reified T> HttpResponse.readOrThrow(): T {
        requireSuccess()
        return try {
            body()
        } catch (e: SerializationException) {
            throw ApiException.SerializationError(errorCause = e)
        } catch (e: ContentConvertException) {
            throw ApiException.SerializationError(errorCause = e)
        }
    }
}
