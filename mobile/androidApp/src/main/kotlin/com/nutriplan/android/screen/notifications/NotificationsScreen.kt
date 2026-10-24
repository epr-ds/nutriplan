@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.notifications

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.android.push.PushPermissionManager
import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.data.model.NotificationPreferences
import com.nutriplan.shared.data.model.UpdateNotificationPreferencesRequest
import com.nutriplan.shared.notifications.NotificationsError
import com.nutriplan.shared.notifications.NotificationsUiState
import com.nutriplan.shared.notifications.NotificationsViewModel
import com.nutriplan.shared.notifications.PushPermissionStatus
import kotlinx.coroutines.launch

/** Test tags for the notification center (used by the Robolectric UI tests). */
object NotificationsTestTags {
    const val LIST = "notifications_list"
    const val LOADING = "notifications_loading"
}

/** Test tags for the permission screens (used by the Robolectric UI tests). */
object NotificationsPermissionTestTags {
    const val ALLOW = "notifications_permission_allow"
    const val NOT_NOW = "notifications_permission_not_now"
    const val OPEN_SETTINGS = "notifications_permission_open_settings"
}

/**
 * Pre-permission priming screen (NTF-504): explains why the app asks for notifications and lets
 * the user allow or defer, before the OS prompt runs.
 */
@Composable
fun NotificationsPermissionScreen(
    onAllow: () -> Unit,
    onNotNow: () -> Unit = {},
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.Default.Notifications,
            contentDescription = stringResource(R.string.notification_center_title),
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(48.dp),
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = stringResource(R.string.notification_permission_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = stringResource(R.string.notification_permission_description),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )

        Spacer(modifier = Modifier.height(24.dp))

        NutriPlanButton(
            onClick = onAllow,
            modifier = Modifier
                .fillMaxWidth()
                .testTag(NotificationsPermissionTestTags.ALLOW),
        ) {
            Text(text = stringResource(R.string.notification_permission_allow))
        }

        Spacer(modifier = Modifier.height(8.dp))

        TextButton(
            onClick = onNotNow,
            modifier = Modifier.testTag(NotificationsPermissionTestTags.NOT_NOW),
        ) {
            Text(text = stringResource(R.string.notification_permission_not_now))
        }
    }
}

/**
 * Post-refusal state of the permission flow (NTF-504): the user declined the OS prompt, so the
 * re-prompt path is the app settings deep link.
 */
@Composable
fun NotificationsPermissionDeniedScreen(
    onOpenSettings: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.Default.Notifications,
            contentDescription = stringResource(R.string.notification_center_title),
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(48.dp),
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = stringResource(R.string.notification_permission_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = stringResource(R.string.notification_permission_denied_description),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )

        Spacer(modifier = Modifier.height(24.dp))

        NutriPlanButton(
            onClick = onOpenSettings,
            modifier = Modifier
                .fillMaxWidth()
                .testTag(NotificationsPermissionTestTags.OPEN_SETTINGS),
        ) {
            Text(text = stringResource(R.string.notification_permission_open_settings))
        }
    }
}

/**
 * The in-app notification center, with its permission flow (NTF-504): before the OS prompt the
 * user sees the priming screen, and after a refusal the re-prompt path is the app settings.
 *
 * Backed by the shared [NotificationsViewModel]; every list action is a callback so the screen
 * stays testable without the Koin graph.
 */
@Composable
fun NotificationsScreen(
    onNotificationClick: (String) -> Unit = {},
) {
    val viewModel = koinInject<NotificationsViewModel>()
    val permissionManager = koinInject<PushPermissionManager>()
    val status by permissionManager.status.collectAsState()
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val permissionLauncher =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            permissionManager.onRequestResult(granted = granted)
        }

    LaunchedEffect(viewModel) { viewModel.load() }

    when (status) {
        // NTF-504: before the OS prompt the user gets the in-app priming screen; after refusal the
        // re-prompt path is the app settings deep link.
        PushPermissionStatus.NOT_ASKED -> NotificationsPermissionScreen(
            onAllow = {
                permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            },
            onNotNow = {},
        )

        PushPermissionStatus.DENIED -> NotificationsPermissionDeniedScreen(
            onOpenSettings = {
                context.startActivity(
                    Intent(
                        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.fromParts("package", context.packageName, null),
                    ),
                )
            },
        )

        PushPermissionStatus.GRANTED, PushPermissionStatus.PROVISIONAL ->
            NotificationsScreenContent(
                state = state,
                onRefresh = { scope.launch { viewModel.refresh() } },
                onRetry = { scope.launch { viewModel.load() } },
                onMarkAsRead = {
                notificationId -> scope.launch { viewModel.markAsRead(notificationId) }
            },
                onNotificationClick = onNotificationClick,
            )
    }
}

/**
 * Stateless notification center: renders [state]; every action is a callback. The loading, error
 * and empty states mirror the meal-plan list (DPL-501) so the two centres feel the same.
 */
@Composable
fun NotificationsScreenContent(
    state: NotificationsUiState,
    onRefresh: () -> Unit,
    onRetry: () -> Unit,
    onMarkAsRead: (String) -> Unit,
    onNotificationClick: (String) -> Unit,
) {
    val error = state.error
    val notifications = state.notifications
    val loadingDescription = stringResource(R.string.cd_notifications_loading)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.notification_center_title),
                        modifier = Modifier.semantics { heading() },
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                ),
            )
        },
    ) { paddingValues ->
        val content = Modifier
            .fillMaxSize()
            .padding(paddingValues)

        when {
            state.isLoading && notifications.isEmpty() -> Box(
                modifier = content.testTag(NotificationsTestTags.LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = loadingDescription },
                )
            }

            error != null && notifications.isEmpty() -> ErrorState(
                message = stringResource(error.messageRes()),
                onRetry = onRetry,
                modifier = content,
                actionLabel = stringResource(R.string.notifications_retry),
            )

            !state.isLoading && error == null && notifications.isEmpty() -> EmptyState(
                title = stringResource(R.string.notification_empty_title),
                description = stringResource(R.string.notification_empty_description),
                modifier = content,
            )

            else -> PullToRefreshBox(
                isRefreshing = state.isRefreshing,
                onRefresh = onRefresh,
                modifier = content,
            ) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .testTag(NotificationsTestTags.LIST),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(notifications, key = { it.id }) { notification ->
                        NotificationCard(
                            notification = notification,
                            onClick = {
                                onMarkAsRead(notification.id)
                                notification.data?.get("deepLink")?.let(onNotificationClick)
                            },
                        )
                    }
                }
            }
        }
    }
}

/**
 * One notification in the center: title, body, and a tap that marks it read and follows the deep
 * link it carries.
 */
@Composable
private fun NotificationCard(
    notification: Notification,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .semantics { contentDescription = "${notification.title}, ${notification.body}" }
            .clickable(onClick = onClick),
        shape = MaterialTheme.shapes.medium,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
        ) {
            Text(
                text = notification.title,
                style = MaterialTheme.typography.titleMedium,
                color = if (notification.isRead) {
                    MaterialTheme.colorScheme.onSurfaceVariant
                } else {
                    MaterialTheme.colorScheme.onSurface
                },
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = notification.body,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
/**
 * Notification preferences screen (NTF-509): per-type + channel toggles and quiet hours, all
 * bound to the shared [NotificationsViewModel]; every change saves with the optimistic + roll-back
 * behaviour the rest of the notification flow uses.
 */
@Composable
fun NotificationsPreferencesScreen(
    onBack: () -> Unit = {},
) {
    val viewModel = koinInject<NotificationsViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()
    val preferences = state.preferences

    LaunchedEffect(Unit) { viewModel.loadPreferences() }

    NotificationsPreferencesScreenContent(
        preferences = preferences,
        onBack = onBack,
        onPushEnabled = { enabled ->
            scope.launch {
                viewModel.updatePreferences(
                    UpdateNotificationPreferencesRequest(
                        pushEnabled = enabled,
                        emailEnabled = preferences?.emailEnabled ?: true,
                        mealReminders = preferences?.mealReminders ?: true,
                        orderUpdates = preferences?.orderUpdates ?: true,
                        promotions = preferences?.promotions ?: true,
                    ),
                )
            }
        },
        onMealRemindersEnabled = { enabled ->
            scope.launch { viewModel.updatePreferences(UpdateNotificationPreferencesRequest(mealReminders = enabled)) }
        },
        onOrderUpdatesEnabled = { enabled ->
            scope.launch { viewModel.updatePreferences(UpdateNotificationPreferencesRequest(orderUpdates = enabled)) }
        },
        onPromotionsEnabled = { enabled ->
            scope.launch { viewModel.updatePreferences(UpdateNotificationPreferencesRequest(promotions = enabled)) }
        },
        onEmailEnabled = { enabled ->
            scope.launch { viewModel.updatePreferences(UpdateNotificationPreferencesRequest(emailEnabled = enabled)) }
        },
        onQuietHoursChange = { start, end ->
            scope.launch { viewModel.updateQuietHours(start, end) }
        },
    )
}

/**
 * Stateless notification preferences screen content (NTF-509 / NTF-606): renders [preferences];
 * every change flows through callbacks so the accessibility checks can render it without the DI
 * graph.
 */
@Composable
fun NotificationsPreferencesScreenContent(
    preferences: NotificationPreferences?,
    onBack: () -> Unit,
    onPushEnabled: (Boolean) -> Unit,
    onMealRemindersEnabled: (Boolean) -> Unit,
    onOrderUpdatesEnabled: (Boolean) -> Unit,
    onPromotionsEnabled: (Boolean) -> Unit,
    onEmailEnabled: (Boolean) -> Unit,
    onQuietHoursChange: (String?, String?) -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.notification_preferences_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.Default.ArrowBack,
                            contentDescription = stringResource(R.string.notification_preferences_back),
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                ),
            )
        },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            PreferenceToggleRow(
                label = stringResource(R.string.notification_preferences_push),
                checked = preferences?.pushEnabled ?: false,
                onCheckedChange = onPushEnabled,
            )

            PreferenceToggleRow(
                label = stringResource(R.string.notification_preferences_meal_reminders),
                checked = preferences?.mealReminders ?: false,
                enabled = preferences?.pushEnabled ?: false,
                onCheckedChange = onMealRemindersEnabled,
            )

            PreferenceToggleRow(
                label = stringResource(R.string.notification_preferences_order_updates),
                checked = preferences?.orderUpdates ?: false,
                enabled = preferences?.pushEnabled ?: false,
                onCheckedChange = onOrderUpdatesEnabled,
            )

            PreferenceToggleRow(
                label = stringResource(R.string.notification_preferences_promotions),
                checked = preferences?.promotions ?: false,
                enabled = preferences?.pushEnabled ?: false,
                onCheckedChange = onPromotionsEnabled,
            )

            PreferenceToggleRow(
                label = stringResource(R.string.notification_preferences_email),
                checked = preferences?.emailEnabled ?: false,
                onCheckedChange = onEmailEnabled,
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = stringResource(R.string.notification_preferences_quiet_hours),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )

            QuietHoursTimeField(
                label = stringResource(R.string.notification_preferences_quiet_hours_start),
                value = preferences?.quietHoursStart,
                onCommit = { start ->
                    // The other slot is preserved: only the edited one is committed as the new value.
                    onQuietHoursChange(start, preferences?.quietHoursEnd)
                },
            )

            QuietHoursTimeField(
                label = stringResource(R.string.notification_preferences_quiet_hours_end),
                value = preferences?.quietHoursEnd,
                onCommit = { end ->
                    onQuietHoursChange(preferences?.quietHoursStart, end)
                },
            )
        }
    }
}

/**
 * One notification preference row: label + switch, disabled while the (parent) push master switch
 * is off so the user cannot edit a type that is not being delivered.
 */
@Composable
private fun PreferenceToggleRow(
    label: String,
    checked: Boolean,
    enabled: Boolean = true,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            modifier = Modifier.weight(1f),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
        )

        Switch(
            checked = checked,
            onCheckedChange = if (enabled) onCheckedChange else null,
            // NTF-606: the switch is labelled by its row text so TalkBack announces it as a toggle.
            modifier = Modifier
                .heightIn(min = 48.dp)
                .semantics { contentDescription = label },
        )
    }
}

/**
 * Quiet-hours slot editor: a plain single-line text field normalized to `HH:mm`. A committed
 * valid time is stored as the slot value (start or end); clearing or partial input clears it, so
 * the quiet-hours window can be set, adjusted or removed.
 */
@Composable
private fun QuietHoursTimeField(
    label: String,
    value: String?,
    onCommit: (String?) -> Unit,
) {
    var text by remember { mutableStateOf(value ?: "") }

    LaunchedEffect(value) { text = value ?: "" }

    OutlinedTextField(
        value = text,
        onValueChange = { newText ->
            text = newText
            normalizeQuietHoursTime(newText)?.let(onCommit)
        },
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
    )
}

/** Normalize a typed quiet-hours time to `HH:mm`; null when the input is not a valid time. */
private fun normalizeQuietHoursTime(raw: String?): String? {
    val digits = raw?.replace(":", "")?.take(4).orEmpty()
    if (digits.length != 4) return null
    val hours = digits.substring(0, 2).toIntOrNull() ?: return null
    val minutes = digits.substring(2, 4).toIntOrNull() ?: return null
    if (hours > 23 || minutes > 59) return null
    return "%02d:%02d".format(hours, minutes)
}
