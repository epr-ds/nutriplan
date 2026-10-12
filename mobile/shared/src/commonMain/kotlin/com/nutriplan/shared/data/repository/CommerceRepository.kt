package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.CreatePaymentMethodRequest
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderQuery
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SyncGroceryRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext

/**
 * Repository for commerce-related API operations.
 *
 * Covers orders, payment methods, and grocery sync.
 */
interface CommerceRepository {

    /** Create a new order. */
    suspend fun createOrder(request: CreateOrderRequest): Order

    /** List orders with optional filters. */
    suspend fun getOrders(query: OrderQuery? = null): List<Order>

    /** Get a specific order by ID. */
    suspend fun getOrder(orderId: String): Order

    /** Cancel an existing order. */
    suspend fun cancelOrder(orderId: String, request: CancelOrderRequest): Order

    /** Sync the grocery list for an order. */
    suspend fun syncGrocery(orderId: String, request: SyncGroceryRequest)

    /** List available payment methods. */
    suspend fun getPaymentMethods(): List<PaymentMethod>

    /** Add a new payment method. */
    suspend fun createPaymentMethod(request: CreatePaymentMethodRequest): PaymentMethod

    /** Delete a payment method. */
    suspend fun deletePaymentMethod(id: String)
}

/**
 * Commerce service API client implementation.
 */
class CommerceRepositoryImpl : CommerceRepository {

    private val client = HttpClientProvider.client

    override suspend fun createOrder(request: CreateOrderRequest): Order {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.COMMERCE}/orders") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun getOrders(query: OrderQuery?): List<Order> {
        return withContext(Dispatchers.IO) {
            val urlBuilder = io.ktor.http.UrlBuilder("${ApiConfig.COMMERCE}/orders")
            query?.let { q ->
                q.status?.let { urlBuilder.appendQueryParameter("status", it) }
                q.limit?.let { urlBuilder.appendQueryParameter("limit", it.toString()) }
                q.offset?.let { urlBuilder.appendQueryParameter("offset", it.toString()) }
            }
            val response = client.get(urlBuilder.buildString())
            handleListResponse<Order>(response)
        }
    }

    override suspend fun getOrder(orderId: String): Order {
        return withContext(Dispatchers.IO) {
            val response = client.get("${ApiConfig.COMMERCE}/orders/$orderId")
            handleResponse(response)
        }
    }

    override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest): Order {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.COMMERCE}/orders/$orderId/cancel") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun syncGrocery(orderId: String, request: SyncGroceryRequest) {
        withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.COMMERCE}/orders/$orderId/grocery/sync") {
                setBody(request)
            }
            if (response.status != HttpStatusCode.OK && response.status != HttpStatusCode.Accepted) {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.bodyAsText(),
                )
            }
        }
    }

    override suspend fun getPaymentMethods(): List<PaymentMethod> {
        return withContext(Dispatchers.IO) {
            val response = client.get("${ApiConfig.COMMERCE}/payment-methods")
            handleListResponse(response)
        }
    }

    override suspend fun createPaymentMethod(request: CreatePaymentMethodRequest): PaymentMethod {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.COMMERCE}/payment-methods") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun deletePaymentMethod(id: String) {
        withContext(Dispatchers.IO) {
            val response = client.delete("${ApiConfig.COMMERCE}/payment-methods/$id")
            if (response.status != HttpStatusCode.OK && response.status != HttpStatusCode.NoContent) {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.bodyAsText(),
                )
            }
        }
    }

    private suspend inline fun <reified T> handleResponse(response: io.ktor.client.statement.HttpResponse): T {
        return when (response.status) {
            HttpStatusCode.OK, HttpStatusCode.Created -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            HttpStatusCode.Forbidden -> throw ApiException.create(
                message = "Forbidden. You don't have permission.",
                code = ApiException.Code.FORBIDDEN,
            )
            HttpStatusCode.NotFound -> throw ApiException.create(
                message = "Resource not found.",
                code = ApiException.Code.NOT_FOUND,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.bodyAsText(),
            )
        }
    }

    private suspend inline fun <reified T> handleListResponse(response: io.ktor.client.statement.HttpResponse): List<T> {
        return when (response.status) {
            HttpStatusCode.OK -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.bodyAsText(),
            )
        }
    }
}
