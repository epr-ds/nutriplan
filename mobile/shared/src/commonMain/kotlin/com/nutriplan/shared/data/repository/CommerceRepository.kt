package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
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
 * Client of the Commerce service (`contracts/commerce.openapi.yaml`, COM-501): orders, saved payment
 * methods and fulfillment (dark-kitchen availability, grocery providers and search). Failures are
 * thrown as [ApiException]; use [com.nutriplan.shared.data.network.toApiFailure] to classify them.
 *
 * The payment and kitchen webhooks in the same document are called by providers, not the app.
 */
interface CommerceRepository {

    /**
     * Create an order from a meal plan (`POST /orders`). With an [idempotencyKey] a retry of the same
     * request returns the original order instead of creating (and charging) a second one; the same
     * key with a different request is a 409.
     */
    suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String? = null): Order

    /** The caller's orders (`GET /orders`), filtered by [query]. */
    suspend fun listOrders(query: OrderListQuery = OrderListQuery()): List<Order>

    /** One of the caller's orders (`GET /orders/{orderId}`); someone else's order is a 404. */
    suspend fun getOrder(orderId: String): Order

    /**
     * Cancel an order (`POST /orders/{orderId}/cancel`). A paid order is refunded in full unless
     * [request] asks for a partial `refundAmount`; an order that can no longer be cancelled is a 409.
     */
    suspend fun cancelOrder(orderId: String, request: CancelOrderRequest? = null): Order

    /**
     * Pull a grocery order's status from its provider (`POST /orders/{orderId}/grocery/sync`). Safe to
     * repeat; an order never placed with a provider is a 409, an unreachable provider a 503.
     */
    suspend fun syncGroceryOrder(orderId: String): Order

    /** The caller's saved payment methods, newest first (`GET /payment-methods`). */
    suspend fun listPaymentMethods(): List<PaymentMethod>

    /** Save a tokenized payment method for reuse (`POST /payment-methods`). */
    suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod

    /** Delete a saved payment method (`DELETE /payment-methods/{paymentMethodId}`). */
    suspend fun deletePaymentMethod(paymentMethodId: String)

    /**
     * Whether a dark kitchen delivers to [zipCode], and its time slots, optionally on [deliveryDate]
     * (ISO date) (`GET /fulfillment/dark-kitchen/availability`).
     */
    suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String? = null): KitchenAvailability

    /** Search products across grocery providers (`POST /fulfillment/grocery/search`). */
    suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider>

    /** The grocery providers available (`GET /fulfillment/grocery/providers`). */
    suspend fun groceryProviders(): List<FulfillmentProvider>
}

class CommerceRepositoryImpl : CommerceRepository {

    private val client = HttpClientProvider.client

    override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.COMMERCE}/orders") {
                idempotencyKey?.let { header(IDEMPOTENCY_KEY, it) }
                setBody(request)
            }.readOrThrow()
        }

    override suspend fun listOrders(query: OrderListQuery): List<Order> =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.COMMERCE}/orders") {
                query.status?.let { parameter("status", it) }
                query.fromDate?.let { parameter("fromDate", it) }
                query.page?.let { parameter("page", it) }
                query.limit?.let { parameter("limit", it) }
            }.readOrThrow()
        }

    override suspend fun getOrder(orderId: String): Order =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.COMMERCE}/orders/${orderId.encodeURLPathPart()}").readOrThrow()
        }

    override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.COMMERCE}/orders/${orderId.encodeURLPathPart()}/cancel") {
                // The body is optional: without one the order is refunded in full.
                request?.let { setBody(it) }
            }.readOrThrow()
        }

    override suspend fun syncGroceryOrder(orderId: String): Order =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.COMMERCE}/orders/${orderId.encodeURLPathPart()}/grocery/sync").readOrThrow()
        }

    override suspend fun listPaymentMethods(): List<PaymentMethod> =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.COMMERCE}/payment-methods").readOrThrow()
        }

    override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.COMMERCE}/payment-methods") { setBody(request) }.readOrThrow()
        }

    override suspend fun deletePaymentMethod(paymentMethodId: String) {
        withContext(Dispatchers.IO) {
            val response = client.delete("${ApiConfig.COMMERCE}/payment-methods/${paymentMethodId.encodeURLPathPart()}")
            if (!response.status.isSuccess()) {
                throw ApiException.HttpError(statusCode = response.status.value, body = response.bodyAsText())
            }
        }
    }

    override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.COMMERCE}/fulfillment/dark-kitchen/availability") {
                parameter("zipCode", zipCode)
                deliveryDate?.let { parameter("deliveryDate", it) }
            }.readOrThrow()
        }

    override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.COMMERCE}/fulfillment/grocery/search") { setBody(request) }.readOrThrow()
        }

    override suspend fun groceryProviders(): List<FulfillmentProvider> =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.COMMERCE}/fulfillment/grocery/providers").readOrThrow()
        }

    /**
     * Decodes a 2xx response into [T]; anything else becomes an [ApiException.HttpError] carrying
     * the status and the (problem+json) body, so it classifies by status. A body that does not match
     * the model becomes an [ApiException.SerializationError] instead of an unexplained crash.
     */
    private suspend inline fun <reified T> HttpResponse.readOrThrow(): T {
        if (!status.isSuccess()) {
            throw ApiException.HttpError(statusCode = status.value, body = bodyAsText())
        }
        return try {
            body()
        } catch (e: SerializationException) {
            throw ApiException.SerializationError(errorCause = e)
        } catch (e: ContentConvertException) {
            throw ApiException.SerializationError(errorCause = e)
        }
    }

    private companion object {
        const val IDEMPOTENCY_KEY = "Idempotency-Key"
    }
}
