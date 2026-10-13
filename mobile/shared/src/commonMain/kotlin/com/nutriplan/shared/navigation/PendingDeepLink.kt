package com.nutriplan.shared.navigation

/**
 * Holds a deep link received from outside the app (notification tap, browser, another app)
 * until the user is allowed to see its target.
 *
 * - Only an allowlist of detail screens can be opened from outside; links to flows such as
 *   login, checkout or profile editing are rejected, because the `nutriplan://` scheme is
 *   exported and any app or web page can fire it.
 * - A link is released only once the user is authenticated, so it can never skip login.
 * - A newer accepted link replaces an older pending one; a rejected link leaves the pending one alone.
 *
 * Not thread-safe: use from the main thread.
 */
class PendingDeepLink {

    private var pending: Route? = null

    /** True while an accepted link is waiting to be opened. */
    val hasPending: Boolean get() = pending != null

    /**
     * Offer a raw link. Returns true if it was accepted as the new pending link.
     */
    fun offer(deepLink: String?): Boolean {
        val route = deepLink?.let(Route::fromDeepLink) ?: return false
        if (!isOpenableFromOutside(route)) return false
        pending = route
        return true
    }

    /**
     * Return and clear the pending route if [isAuthenticated]; otherwise keep it for later
     * (for example until login completes) and return null.
     */
    fun takeIfAuthenticated(isAuthenticated: Boolean): Route? {
        if (!isAuthenticated) return null
        return pending.also { pending = null }
    }

    /** Drop any pending link (for example on logout). */
    fun clear() {
        pending = null
    }

    private fun isOpenableFromOutside(route: Route): Boolean = when (route) {
        is Route.DeepLinkMeal,
        is Route.DeepLinkPlan,
        is Route.DeepLinkOrder,
        is Route.MealPlanDetail,
        is Route.RecipeDetail,
        is Route.OrderDetail,
        Route.NotificationCenter,
        -> true
        else -> false
    }
}
