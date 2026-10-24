package com.nutriplan.shared.notifications

/**
 * Whether the user has answered the OS notification permission prompt (NTF-504).
 *
 * - [NOT_ASKED]: the app has not asked yet, or the answer is still pending behind the OS dialog.
 * - [GRANTED]: the user allowed notifications.
 * - [DENIED]: the user refused the OS prompt (the re-prompt path is the system settings deep link).
 * - [PROVISIONAL]: the user accepted quiet/provisional access (iOS), which lets alerts through
 *   without the full badge/sound treatment until the user opts in later.
 */
enum class PushPermissionStatus {
    NOT_ASKED,
    GRANTED,
    DENIED,
    PROVISIONAL,
}

/** Whether the user allows notifications to reach them (provisional access on iOS counts). */
val PushPermissionStatus.isGrantedOrProvisional: Boolean
    get() = this == PushPermissionStatus.GRANTED || this == PushPermissionStatus.PROVISIONAL