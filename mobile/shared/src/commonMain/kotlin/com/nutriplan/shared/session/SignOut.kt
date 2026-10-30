package com.nutriplan.shared.session

import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.local.OrderCache
import com.nutriplan.shared.data.local.PendingChangeStore
import com.nutriplan.shared.data.local.PendingMealStore
import com.nutriplan.shared.data.local.RecipeCache
import com.nutriplan.shared.data.local.SavedAddressStore
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.recipes.FavoriteRecipesViewModel

/**
 * Ends the user's session: forgets the tokens (including the copy in secure storage) and wipes
 * locally cached personal data, so the next person using the device never sees it.
 */
class SignOut(
    private val authRepository: AuthRepository,
    private val mealPlanCache: MealPlanCache,
    private val favorites: FavoriteRecipesViewModel,
    private val pendingMeals: PendingMealStore? = null,
    private val pendingChanges: PendingChangeStore? = null,
    private val orders: OrderCache? = null,
    private val addresses: SavedAddressStore? = null,
    private val recipes: RecipeCache? = null,
) {
    operator fun invoke() {
        // Tokens first: if wiping the cache fails the session is still over.
        authRepository.clearTokens()
        runCatching { mealPlanCache.clear() }
        runCatching { favorites.reset() }
        runCatching { pendingMeals?.clear() }
        runCatching { pendingChanges?.clear() }
        // COM-503: orders and delivery addresses are the signed-out user's too.
        runCatching { orders?.clear() }
        runCatching { addresses?.clear() }
        // DPL-403: the cached recipe catalog is the signed-out user's too.
        runCatching { recipes?.clear() }
        SessionEvents.emitSignedOut()
    }
}
