package com.nutriplan.android.i18n

import androidx.annotation.StringRes
import com.nutriplan.android.R
import com.nutriplan.shared.auth.AuthError
import com.nutriplan.shared.auth.FieldError
import com.nutriplan.shared.onboarding.OnboardingError
import com.nutriplan.shared.planning.MealPlanDetailError
import com.nutriplan.shared.planning.MealPlanListError

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
