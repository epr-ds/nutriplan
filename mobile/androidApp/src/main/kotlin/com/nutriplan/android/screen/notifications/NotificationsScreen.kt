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
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
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