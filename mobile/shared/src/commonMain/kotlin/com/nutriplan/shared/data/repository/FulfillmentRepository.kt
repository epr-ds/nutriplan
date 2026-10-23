package com.nutriplan.shared.data.repository

import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.commerce.isMexicanZipCode
import com.nutriplan.shared.commerce.toOrderError
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchItem
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import kotlin.coroutines.cancellation.CancellationException

/**
 * The fulfillment options for an order (COM-505), shared by the Compose and SwiftUI checkout:
 * whether a dark kitchen delivers to a zip code and when, which grocery providers there are, and
 * which of them can supply a list of ingredients. Every query returns an [OrderResult] instead of
 * throwing, with failures mapped to the same [OrderError]s as orders.
 *
 * These answers change with the kitchen's capacity and the providers' stock, so they are always
 * asked of the server, never cached. Input the server would refuse anyway -- a zip code that is not
 * five digits, a search with no ingredient -- is [OrderError.REJECTED] without a call.
 */
class FulfillmentRepository(private val remote: CommerceRepository) {

    /**
     * Whether a dark kitchen delivers to [zipCode] and its time slots, optionally on [deliveryDate]
     * (ISO date). An area it does not serve is a success with `available` false, not a failure.
     */
    suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String? = null): OrderResult<KitchenAvailability> {
        val zip = zipCode.trim()
        if (!zip.isMexicanZipCode()) return OrderResult.Failure(OrderError.REJECTED)
        return query { remote.darkKitchenAvailability(zip, deliveryDate?.trim()?.takeIf(String::isNotEmpty)) }
    }

    /** The grocery providers enabled for this environment, in the server's order. */
    suspend fun groceryProviders(): OrderResult<List<FulfillmentProvider>> = query { remote.groceryProviders() }

    /**
     * The grocery providers that can supply [items] for delivery to [zipCode], optionally only among
     * [providers] (provider ids). Ingredient names are trimmed and lines without one are dropped;
     * nothing left to search for is [OrderError.REJECTED]. An empty answer means no provider has
     * them, which is a success.
     */
    suspend fun searchGrocery(
        items: List<GrocerySearchItem>,
        zipCode: String,
        providers: List<String> = emptyList(),
    ): OrderResult<List<FulfillmentProvider>> {
        val zip = zipCode.trim()
        val wanted = items.mapNotNull { item ->
            item.ingredient?.trim()?.takeIf(String::isNotEmpty)?.let { item.copy(ingredient = it) }
        }
        if (wanted.isEmpty() || !zip.isMexicanZipCode()) return OrderResult.Failure(OrderError.REJECTED)
        val only = providers.map(String::trim).filter(String::isNotEmpty).distinct()
        return query {
            remote.searchGroceryProducts(
                GrocerySearchRequest(items = wanted, providers = only.takeIf { it.isNotEmpty() }, zipCode = zip),
            )
        }
    }

    /** Run a server call, turning a failure into a typed result (cancellation is never swallowed). */
    private suspend fun <T> query(call: suspend () -> T): OrderResult<T> =
        try {
            OrderResult.Success(call())
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            OrderResult.Failure(e.toOrderError())
        }
}
