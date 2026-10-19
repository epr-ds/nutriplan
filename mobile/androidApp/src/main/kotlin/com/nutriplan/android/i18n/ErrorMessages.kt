package com.nutriplan.android.i18n

import androidx.annotation.StringRes
import com.nutriplan.android.R
import com.nutriplan.shared.auth.AuthError
import com.nutriplan.shared.auth.FieldError
import com.nutriplan.shared.onboarding.OnboardingError
import com.nutriplan.shared.planning.AddMealError
import com.nutriplan.shared.planning.AddMealFieldError
import com.nutriplan.shared.planning.EditMealError
import com.nutriplan.shared.planning.EditMealFieldError
import com.nutriplan.shared.planning.MealPlanDetailError
import com.nutriplan.shared.planning.MealPlanFormError
import com.nutriplan.shared.planning.MealPlanListError
import com.nutriplan.shared.planning.PlanFieldError
import com.nutriplan.shared.recipes.FavoriteError
import com.nutriplan.shared.recipes.RecipeDetailError
import com.nutriplan.shared.recipes.RecipeListError

/** DPL-607: message for a favorites list that could not be loaded. */
@StringRes
fun FavoriteError.loadMessageRes(): Int = when (this) {
    FavoriteError.NETWORK -> R.string.error_favorites_load_network
    FavoriteError.SERVER_PROBLEM -> R.string.error_favorites_load_server
    FavoriteError.SESSION_EXPIRED -> R.string.error_favorites_session_expired
    FavoriteError.UNKNOWN -> R.string.error_favorites_load_unknown
}

/** DPL-607: message for a heart that was put back because saving or removing a favorite failed. */
@StringRes
fun FavoriteError.changeMessageRes(): Int = when (this) {
    FavoriteError.NETWORK -> R.string.error_favorite_change_network
    FavoriteError.SERVER_PROBLEM -> R.string.error_favorite_change_server
    FavoriteError.SESSION_EXPIRED -> R.string.error_favorites_session_expired
    FavoriteError.UNKNOWN -> R.string.error_favorite_change_unknown
}

/** DPL-508: inline message for one invalid field of the edit-meal form. */
@StringRes
fun EditMealFieldError.messageRes(): Int = when (this) {
    EditMealFieldError.SERVINGS_REQUIRED -> R.string.error_add_meal_servings_required
    EditMealFieldError.SERVINGS_INVALID -> R.string.error_add_meal_servings_invalid
}

/** DPL-508: message for a meal that could not be loaded, changed or removed. */
@StringRes
fun EditMealError.messageRes(): Int = when (this) {
    EditMealError.NETWORK -> R.string.error_edit_meal_network
    EditMealError.SERVER_PROBLEM -> R.string.error_edit_meal_server
    EditMealError.SESSION_EXPIRED -> R.string.error_edit_meal_session_expired
    EditMealError.NOT_FOUND -> R.string.error_edit_meal_not_found
    EditMealError.REJECTED -> R.string.error_edit_meal_rejected
    EditMealError.UNKNOWN -> R.string.error_edit_meal_unknown
}

/** DPL-507: inline message for one invalid field of the add-meal form. */
@StringRes
fun AddMealFieldError.messageRes(): Int = when (this) {
    AddMealFieldError.MEAL_TYPE_REQUIRED -> R.string.error_add_meal_type_required
    AddMealFieldError.SERVINGS_REQUIRED -> R.string.error_add_meal_servings_required
    AddMealFieldError.SERVINGS_INVALID -> R.string.error_add_meal_servings_invalid
}

/** DPL-507: message for a recipe that could not be loaded, or a meal that could not be added. */
@StringRes
fun AddMealError.messageRes(): Int = when (this) {
    AddMealError.NETWORK -> R.string.error_add_meal_network
    AddMealError.SERVER_PROBLEM -> R.string.error_add_meal_server
    AddMealError.SESSION_EXPIRED -> R.string.error_add_meal_session_expired
    AddMealError.NOT_FOUND -> R.string.error_add_meal_not_found
    AddMealError.REJECTED -> R.string.error_add_meal_rejected
    AddMealError.UNKNOWN -> R.string.error_add_meal_unknown
}

/** DPL-601: message for a recipe search that failed. */
@StringRes
fun RecipeListError.messageRes(): Int = when (this) {
    RecipeListError.NETWORK -> R.string.error_recipes_network
    RecipeListError.SERVER_PROBLEM -> R.string.error_recipes_server
    RecipeListError.SESSION_EXPIRED -> R.string.error_recipes_session_expired
    RecipeListError.UNKNOWN -> R.string.error_recipes_unknown
}

/** DPL-603: message for a recipe that could not be loaded. */
@StringRes
fun RecipeDetailError.messageRes(): Int = when (this) {
    RecipeDetailError.NETWORK -> R.string.error_recipe_detail_network
    RecipeDetailError.SERVER_PROBLEM -> R.string.error_recipe_detail_server
    RecipeDetailError.NOT_FOUND -> R.string.error_recipe_detail_not_found
    RecipeDetailError.SESSION_EXPIRED -> R.string.error_recipe_detail_session_expired
    RecipeDetailError.UNKNOWN -> R.string.error_recipe_detail_unknown
}

/** Localized name of a diet type as sent by the server; unknown types are shown as sent. */
@StringRes
fun dietTypeLabelRes(dietType: String): Int? = when (dietType.lowercase()) {
    "omnivore" -> R.string.diet_omnivore
    "vegetarian" -> R.string.diet_vegetarian
    "vegan" -> R.string.diet_vegan
    "keto" -> R.string.diet_keto
    "paleo" -> R.string.diet_paleo
    else -> null
}

/** DPL-503: inline message for one invalid field of the create-plan form. */
@StringRes
fun PlanFieldError.messageRes(): Int = when (this) {
    PlanFieldError.NAME_REQUIRED -> R.string.error_plan_name_required
    PlanFieldError.START_DATE_REQUIRED -> R.string.error_plan_start_required
    PlanFieldError.END_DATE_REQUIRED -> R.string.error_plan_end_required
    PlanFieldError.END_BEFORE_START -> R.string.error_plan_end_before_start
    PlanFieldError.CALORIES_REQUIRED -> R.string.error_plan_calories_required
    PlanFieldError.CALORIES_INVALID -> R.string.error_plan_calories_invalid
}

/** DPL-503: message for a create-plan request that failed. */
@StringRes
fun MealPlanFormError.messageRes(): Int = when (this) {
    MealPlanFormError.NETWORK -> R.string.error_plan_form_network
    MealPlanFormError.SERVER_PROBLEM -> R.string.error_plan_form_server
    MealPlanFormError.SESSION_EXPIRED -> R.string.error_plan_form_session_expired
    MealPlanFormError.REJECTED -> R.string.error_plan_form_rejected
    MealPlanFormError.UNKNOWN -> R.string.error_plan_form_unknown
}

/**
 * DPL-501: message for a failed meal plan load. When [hasSavedPlans] the list is still shown from
 * the device, so the message says so instead of blocking the screen.
 */
@StringRes
fun MealPlanListError.messageRes(hasSavedPlans: Boolean): Int = when (this) {
    MealPlanListError.NETWORK ->
        if (hasSavedPlans) R.string.error_plans_network_saved else R.string.error_plans_network
    MealPlanListError.SERVER_PROBLEM ->
        if (hasSavedPlans) R.string.error_plans_server_saved else R.string.error_plans_server
    MealPlanListError.SESSION_EXPIRED -> R.string.error_plans_session_expired
    MealPlanListError.UNKNOWN -> R.string.error_plans_unknown
}

/**
 * DPL-505: message for a failed plan detail load. When [hasSavedPlan] the plan is still shown from
 * the device, so the message says so instead of blocking the screen.
 */
@StringRes
fun MealPlanDetailError.messageRes(hasSavedPlan: Boolean): Int = when (this) {
    MealPlanDetailError.NETWORK ->
        if (hasSavedPlan) R.string.error_plan_detail_network_saved else R.string.error_plan_detail_network
    MealPlanDetailError.SERVER_PROBLEM ->
        if (hasSavedPlan) R.string.error_plan_detail_server_saved else R.string.error_plan_detail_server
    MealPlanDetailError.NOT_FOUND -> R.string.error_plan_detail_not_found
    MealPlanDetailError.SESSION_EXPIRED -> R.string.error_plan_detail_session_expired
    MealPlanDetailError.UNKNOWN -> R.string.error_plan_detail_unknown
}

/** Localized name of a meal type as sent by the server; unknown types are shown as sent. */
@StringRes
fun mealTypeLabelRes(mealType: String): Int? = when (mealType.uppercase()) {
    "BREAKFAST" -> R.string.meal_type_breakfast
    "LUNCH" -> R.string.meal_type_lunch
    "DINNER" -> R.string.meal_type_dinner
    "SNACK" -> R.string.meal_type_snack
    else -> null
}

/** Localized name of a plan status as sent by the server; unknown statuses are shown as sent. */
@StringRes
fun planStatusLabelRes(status: String): Int? = when (status.lowercase()) {
    "draft" -> R.string.plan_status_draft
    "active" -> R.string.plan_status_active
    "completed" -> R.string.plan_status_completed
    "saved" -> R.string.plan_status_saved
    else -> null
}

/**
 * IDN-902: maps the shared layer's stable error codes to localized Android string resources.
 *
 * The shared view-models emit locale-neutral codes; the platform owns the es/en microcopy.
 */
@StringRes
fun FieldError.messageRes(): Int = when (this) {
    FieldError.NAME_REQUIRED -> R.string.error_field_name_required
    FieldError.NAME_TOO_SHORT -> R.string.error_field_name_too_short
    FieldError.EMAIL_REQUIRED -> R.string.error_field_email_required
    FieldError.EMAIL_INVALID -> R.string.error_field_email_invalid
    FieldError.PASSWORD_REQUIRED -> R.string.error_field_password_required
    FieldError.PASSWORD_TOO_SHORT -> R.string.error_field_password_too_short
    FieldError.CONFIRM_PASSWORD_REQUIRED -> R.string.error_field_confirm_password_required
    FieldError.CONFIRM_PASSWORD_MISMATCH -> R.string.error_field_confirm_password_mismatch
}

@StringRes
fun AuthError.messageRes(): Int = when (this) {
    AuthError.INVALID_CREDENTIALS -> R.string.error_auth_invalid_credentials
    AuthError.TOO_MANY_ATTEMPTS -> R.string.error_auth_too_many_attempts
    AuthError.SERVER_PROBLEM -> R.string.error_auth_server_problem
    AuthError.LOGIN_FAILED -> R.string.error_auth_login_failed
    AuthError.NETWORK -> R.string.error_auth_network
    AuthError.UNKNOWN -> R.string.error_auth_unknown
}

@StringRes
fun OnboardingError.messageRes(): Int = when (this) {
    OnboardingError.SAVE_FAILED -> R.string.error_onboarding_save_failed
}
