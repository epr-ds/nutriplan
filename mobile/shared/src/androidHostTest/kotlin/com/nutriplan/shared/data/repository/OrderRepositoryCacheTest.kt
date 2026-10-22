package com.nutriplan.shared.data.repository

import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.data.local.OrderCache
import com.nutriplan.shared.data.local.SavedAddressStore
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.testing.newDatabase
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.utils.io.errors.IOException
import kotlinx.coroutines.flow.last
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * COM-504 end to end on the device's real storage: the Commerce client (over a mock engine), the
 * SQLite [OrderCache] and the [SavedAddressStore]. Orders read online are there offline, and a placed
 * order's address lands in the address book.
 */
class OrderRepositoryCacheTest {

    private val database = newDatabase()
    private var online = true
    private var reply = """[{"id":"o2","status":"pending","total":{"amount":208.0,"currency":"MXN","formatted":"MXN 208.00"}},""" +
        """{"id":"o1","status":"delivered"}]"""
    private var status = HttpStatusCode.OK

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun repository(): OrderRepository {
        HttpClientProvider.create(
            MockEngine {
                if (!online) throw IOException("no route to host")
                respond(content = reply, status = status, headers = headersOf(HttpHeaders.ContentType, "application/json"))
            },
            authRepository = null,
        )
        return OrderRepository(CommerceRepositoryImpl(), OrderCache(database), SavedAddressStore(database))
    }

    @Test
    fun `orders read online are served from the device when offline`() = runTest {
        val orders = repository()
        val first = orders.orders().last() as OrderResult.Success
        assertTrue(first.value.fresh)

        online = false
        val offline = orders.orders().last() as OrderResult.Success

        assertEquals(listOf("o2", "o1"), offline.value.value.map { it.id })
        assertEquals("MXN 208.00", offline.value.value.first().total?.formatted)
        assertEquals(OrderError.NETWORK, offline.value.refreshError)
    }

    @Test
    fun `the copy survives a restart of the app`() = runTest {
        repository().orders().last()

        online = false
        // A new repository and cache over the same database, as after the app is reopened offline.
        val reopened = OrderRepository(CommerceRepositoryImpl(), OrderCache(database))
        val delivered = reopened.orders(status = "delivered").last() as OrderResult.Success

        assertEquals(listOf("o1"), delivered.value.value.map { it.id })
    }

    @Test
    fun `a placed order is stored and its address saved for the next checkout`() = runTest {
        val address = OrderAddress(street = "Reforma 222", city = "CDMX", state = "CDMX", zipCode = "06600", country = "MX")
        reply = """{"id":"new","status":"pending"}"""
        status = HttpStatusCode.Created
        val orders = repository()

        val placed = orders.createOrder(
            CreateOrderRequest(
                mealPlanId = "p1",
                fulfillmentType = "pickup",
                deliveryAddress = address,
                deliveryDate = "2026-11-02",
                deliveryTimeSlot = "13:00-15:00",
            ),
        )

        assertEquals("new", (placed as OrderResult.Success).value.id)
        assertEquals("new", OrderCache(database).getOrder("new")?.id)
        assertEquals(address, SavedAddressStore(database).preferred()?.address)
    }
}
