package com.nutriplan.android.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.nutriplan.android.MainActivity
import com.nutriplan.android.R
import com.nutriplan.shared.data.repository.NotificationRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.koin.core.context.GlobalContext

/** Channel for tray notifications posted by the push service (Android 8+). */
private const val CHANNEL_ID = "nutriplan_push"

private const val NOTIFICATION_ID = 1001

private const val REQUEST_CODE_PUSH = 4242

/** Data key the notification service puts the deep link under (NTF-304). */
private const val DEEP_LINK_KEY = "deepLink"

/** Platform label used when registering the FCM token with the backend (NTF-501). */
private const val PLATFORM_ANDROID = "android"

/**
 * Firebase Cloud Messaging handling for the NutriPlan Android app (NTF-502).
 *
 * Receives push through the `com.google.firebase.MESSAGING_EVENT` intent filter, forwards fresh
 * tokens to the backend through the shared notification repository (NTF-501), and presents
 * notification messages while the app is in the foreground. Background notification-only messages
 * are displayed by the system tray, which is why the foreground branch is what posts here.
 */
class NutriPlanMessagingService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            runCatching {
                GlobalContext.get().get<NotificationRepository>().registerDevice(
                    platform = PLATFORM_ANDROID,
                    token = token,
                )
            }
        }
    }

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        val deepLink = remoteMessage.data[DEEP_LINK_KEY]?.takeIf { it.isNotBlank() }
        val notification = remoteMessage.notification

        when {
            deepLink != null -> {
                if (notification != null && isAppInForeground()) {
                    showNotification(notification, deepLinkPendingIntent(deepLink))
                } else {
                    startDeepLinkActivity(deepLink)
                }
            }

            notification != null && isAppInForeground() -> {
                showNotification(notification, launchPendingIntent())
            }
        }
    }

    /** Whether the app process is in the foreground (at least resumed). */
    private fun isAppInForeground(): Boolean =
        ProcessLifecycleOwner.get().lifecycle.currentState == Lifecycle.State.RESUMED

    /** Open the app at the deep-linked screen (order, plan or meal; NTF-304). */
    private fun startDeepLinkActivity(deepLink: String) {
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                data = Uri.parse(deepLink)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
        )
    }

    /** Post one tray notification through the NutriPlan push channel. */
    private fun showNotification(
        notification: RemoteMessage.Notification,
        contentIntent: PendingIntent,
    ) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            // Notification channels are Android 8+; below that there is no channel to post to.
            return
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = manager.getNotificationChannel(CHANNEL_ID)
        if (channel == null) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.notification_center_title),
                    NotificationManager.IMPORTANCE_DEFAULT,
                ),
            )
        }

        val title = notification.title?.toString()
            ?: getString(R.string.notification_center_title)
        val body = notification.body?.toString() ?: ""

        manager.notify(
            NOTIFICATION_ID,
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(title)
                .setContentText(body)
                .setContentIntent(contentIntent)
                .setAutoCancel(true)
                .build(),
        )
    }

    /** Content intent that opens the app at the deep-linked screen. */
    private fun deepLinkPendingIntent(deepLink: String): PendingIntent =
        PendingIntent.getActivity(
            this,
            REQUEST_CODE_PUSH,
            Intent(this, MainActivity::class.java).apply {
                data = Uri.parse(deepLink)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    /** Content intent that opens the app (launcher entry point). */
    private fun launchPendingIntent(): PendingIntent =
        PendingIntent.getActivity(
            this,
            REQUEST_CODE_PUSH,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
}