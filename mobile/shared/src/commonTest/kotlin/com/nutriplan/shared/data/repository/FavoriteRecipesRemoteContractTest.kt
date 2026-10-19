package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.network.toApiFailure
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.utils.io.errors.IOException
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * [FavoriteRecipesRemoteImpl] against the favorites part of `contracts/dietary.openapi.yaml`: the
 * request it sends (method, path, query), how it reads the list and the empty `204`s, and how
 * failures are classified. A [MockEngine] stands in for the server.
 */
class FavoriteRecipesRemoteContractTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")
    private val problemHeaders = headersOf(HttpHeaders.ContentType, "application/problem+json")

    private var lastRequest: HttpRequestData? = null

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun serve(
        status: HttpStatusCode = HttpStatusCode.OK,
        body: String = "",
        headers: io.ktor.http.Headers = jsonHeaders,
    ): FavoriteRecipesRemoteImpl {
        HttpClientProvider.create(
            MockEngine { request ->
                lastRequest = request
                respond(content = body, status = status, headers = headers)
            },
            authRepository = null,
        )
        return FavoriteRecipesRemoteImpl()
    }

    @Test
    fun `list asks for the contract's paging parameters`() = runTest {
        val remote = serve(body = "[]")

        remote.list(page = 2, limit = 50)

        val request = lastRequest!!
        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/dietary/v1/favorites", request.url.encodedPath)
        assertEquals("2", request.url.parameters["page"])
        assertEquals("50", request.url.parameters["limit"])
    }

    @Test
    fun `list defaults to the first page of the largest size`() = runTest {
        val remote = serve(body = "[]")

        remote.list()

        assertEquals("1", lastRequest!!.url.parameters["page"])
        assertEquals("100", lastRequest!!.url.parameters["limit"])
    }

    @Test
    fun `list decodes contract-shaped recipes`() = runTest {
        val remote = serve(
            body = """
                [{"id":"r1","name":"Soup","servings":2,"ingredients":[{"name":"Water"}],
                  "instructions":["Boil"],"dietaryTypes":["vegan"],
                  "nutritionalInfo":{"calories":120,"protein":4.5}},
                 {"id":"r2","name":"Stew","servings":4}]
            """.trimIndent(),
        )

        val recipes = remote.list()

        assertEquals(listOf("r1", "r2"), recipes.map { it.id })
        assertEquals(120, recipes[0].nutritionalInfo?.calories)
        assertEquals(listOf("vegan"), recipes[0].dietaryTypes)
        assertTrue(recipes[1].ingredients.isEmpty())
    }

    @Test
    fun `add puts the recipe id in the path and accepts the empty 204`() = runTest {
        val remote = serve(status = HttpStatusCode.NoContent)

        remote.add("r1")

        assertEquals(HttpMethod.Put, lastRequest!!.method)
        assertEquals("/dietary/v1/favorites/r1", lastRequest!!.url.encodedPath)
    }

    @Test
    fun `remove deletes by recipe id and accepts the empty 204`() = runTest {
        val remote = serve(status = HttpStatusCode.NoContent)

        remote.remove("r1")

        assertEquals(HttpMethod.Delete, lastRequest!!.method)
        assertEquals("/dietary/v1/favorites/r1", lastRequest!!.url.encodedPath)
    }

    @Test
    fun `an id with a slash is escaped in the path`() = runTest {
        val remote = serve(status = HttpStatusCode.NoContent)

        remote.add("a/b")

        assertEquals("/dietary/v1/favorites/a%2Fb", lastRequest!!.url.encodedPath)
    }

    @Test
    fun `saving an unknown recipe is classified as not found`() = runTest {
        val remote = serve(
            status = HttpStatusCode.NotFound,
            body = """{"type":"about:blank","title":"Not Found","status":404}""",
            headers = problemHeaders,
        )

        val error = assertFailsWith<ApiException.HttpError> { remote.add("gone") }

        assertEquals(ApiFailure.NOT_FOUND, error.toApiFailure())
    }

    @Test
    fun `every HTTP failure classifies by status`() = runTest {
        val expected = mapOf(
            HttpStatusCode.Unauthorized to ApiFailure.SESSION_EXPIRED,
            HttpStatusCode.UnprocessableEntity to ApiFailure.REJECTED,
            HttpStatusCode.InternalServerError to ApiFailure.SERVER,
        )

        expected.forEach { (status, failure) ->
            val remote = serve(status = status, body = "{}", headers = problemHeaders)
            val error = assertFailsWith<ApiException.HttpError>("status ${status.value}") { remote.list() }
            assertEquals(failure, error.toApiFailure(), "status ${status.value}")
        }
    }

    @Test
    fun `a body that is not a recipe list is a serialization error`() = runTest {
        val remote = serve(body = """{"not":"a list"}""")

        assertFailsWith<ApiException.SerializationError> { remote.list() }
    }

    @Test
    fun `a dropped connection is a network error`() = runTest {
        HttpClientProvider.create(MockEngine { throw IOException("no route to host") }, authRepository = null)
        val remote = FavoriteRecipesRemoteImpl()

        val error = assertFailsWith<ApiException.NetworkError> { remote.remove("r1") }

        assertEquals(ApiFailure.OFFLINE, error.toApiFailure())
    }
}
