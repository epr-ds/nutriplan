import SwiftUI
import Shared
import UIKit
import UserNotifications

private let greeting = Greeting().greet()

/// Destinations for the notification deep-link surface (NTF-508): the in-app notification center is
/// live, the preferences screen is the second destination of the notification surface, and detail
/// screens a deep link opens (meal / plan / order) become destinations here as those screens land
/// in the SwiftUI app.
private enum DeepLinkRoute: Hashable {
    case notifications
    case preferences
}

struct ContentView: View {
    @State private var authorizationStatus: UNNotificationSettings.AuthorizationStatus = .notDetermined
    @State private var hasRequested = false
    @State private var path = [DeepLinkRoute]()

    /// Shared deep-link router (NTF-508): accepts a tapped push deep link and holds it until the
    /// user may open its target; an unknown or unopenable link falls back to the notification
    /// center.
    private let deepLinkRouter = PendingDeepLink()

    init() {
        // NTF-504: the manager reports the authorization status back into the UI.
        PushNotificationManager.shared.onAuthorizationChange = { status in
            authorizationStatus = status
        }
        // NTF-508: a tapped push resolves its deep link through the shared router (cold start and
        // warm start alike land here); an unopenable link falls back to the notification center.
        PushNotificationManager.shared.onNotificationTap = { deepLink in
            if !deepLinkRouter.offer(deepLink: deepLink) {
                path = [DeepLinkRoute.notifications]
            }
        }
    }

    var body: some View {
        Group {
            if authorizationStatus == .notDetermined && !hasRequested {
                NotificationPermissionView(
                    onAllow: {
                        hasRequested = true
                        PushNotificationManager.shared.requestAuthorization { granted, error in
                            if error == nil {
                                PushNotificationManager.shared.refreshAuthorizationStatus()
                            }
                        }
                    },
                    onNotNow: {
                        hasRequested = true
                    },
                )
            } else {
                NavigationStack(path: $path) {
                    HomeContent(
                        onOpenNotifications: { path = [DeepLinkRoute.notifications] },
                    )
                }
                .navigationDestination(for: DeepLinkRoute.self) { route in
                    switch route {
                    case .notifications:
                        NotificationsView(
                            onClose: { path = [] },
                            onOpenPreferences: { path = [DeepLinkRoute.preferences] },
                        )
                    case .preferences:
                        NotificationsPreferencesView(onClose: { path = [] })
                    }
                }
            }
        }
    }
}

/// The signed-in home: the greeting and the entry point to the in-app notification center, with
/// the unread badge (NTF-507).
private struct HomeContent: View {
    @StateObject private var notificationsViewModel: NotificationsViewModel = createNotificationsViewModel()
    @State private var unreadCount = 0
    let onOpenNotifications: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            HStack(spacing: 12) {
                Text("NutriPlan")
                    .font(.title2)
                    .bold()
                Spacer()
                Button {
                    onOpenNotifications()
                } label: {
                    ZStack {
                        Image(systemName: "bell")
                            .font(.subheadline)
                            .foregroundColor(.primary)
                        if unreadCount > 0 {
                            Circle()
                                .fill(Color.red)
                                .frame(width: 8, height: 8)
                        }
                    }
                }
            }
            Spacer(minLength: 24)
            Text(greeting)
                .font(.title)
                .multilineTextAlignment(.center)
        }
        .task {
            await notificationsViewModel.load()
            unreadCount = notificationsViewModel.currentState().unreadCount
        }
    }
}

/// Pre-permission priming screen (NTF-504): the user is asked before the OS prompt runs.
struct NotificationPermissionView: View {
    let onAllow: () -> Void
    let onNotNow: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "bell.fill")
                .font(.system(size: 48))
                .foregroundColor(.orange)
            Text("Stay notified about meal plan reminders and order updates.")
                .font(.headline)
                .multilineTextAlignment(.center)
            Button("Allow Notifications") {
                onAllow()
            }
            Button("Not now") {
                onNotNow()
            }
            Spacer()
        }
        .padding()
    }
}

#Preview {
    ContentView()
}