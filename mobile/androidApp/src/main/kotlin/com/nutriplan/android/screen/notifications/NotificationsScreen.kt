@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.notifications

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.notifications.NotificationsUiState
import com.nutriplan.shared.notifications.NotificationsViewModel
import kotlinx.coroutines.launch

/** Test tags for the notification center (used by the Robolectric UI tests). */
object NotificationsTestTags {
    const val LIST = "notifications_list"
    const val LOADING = "notifications_loading"
}

/**
 * The in-app notification center (NTF-506): the user's notifications, with a loading state, an
 * error state with retry, an empty state, and pull-to-refresh.
 *
 * Backed by the shared [NotificationsViewModel]; every list action is a callback so the screen
 * stays testable without the Koin graph.
 */
@Composable
fun NotificationsScreen(
    onNotificationClick: (String) -> Unit = {},
) {
    val viewModel = koinInject<NotificationsViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { viewModel.load() }

    NotificationsScreenContent(
        state = state,
        onRefresh = { scope.launch { viewModel.refresh() } },
        onRetry = { scope.launch { viewModel.load() } },
        onMarkAsRead = { notificationId -> scope.launch { viewModel.markAsRead(notificationId) } },
        onNotificationClick = onNotificationClick,
    )
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