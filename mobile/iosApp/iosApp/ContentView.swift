import SwiftUI
import Shared
import UIKit
import UserNotifications

private let greeting = Greeting().greet()

/// Destinations for the notification deep-link surface (NTF-508): the in-app notification center is
/// live, the preferences screen is the second destination of the notification surface, the orders
/// list is the third one, and a deep link that opens an order becomes a fourth destination as that
/// screen lands in the SwiftUI app. The checkout (COM-606) is the fifth: it is reached from the
/// orders list, which repeats an order's delivery, not from outside. The login screen (IDN-502) is
/// the sixth: it is the in-app auth destination, not a deep-link one.
private enum DeepLinkRoute: Hashable {
    case notifications
    case preferences
    case orders
    case order(String)
    case checkout(String?, String?)
    case auth
    case register
    case oauth
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
                        onOpenOrders: { path = [DeepLinkRoute.orders] },
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
                    case .orders:
                        OrdersListView(
                            onBack: { path = [] },
                            onOrderClick: { orderId in path = [.order(orderId)] },
                            onReorder: { orderId in path = [.checkout(nil, orderId)] },
                        )
                    case .order(let orderId):
                        OrderDetailView(
                            orderId: orderId,
                            onBack: { path = [] },
                        )
                    case .checkout(let planId, let reorderOrderId):
                        CheckoutView(
                            planId: planId,
                            reorderOrderId: reorderOrderId,
                            onBack: { path = [] },
                            onOrderPlaced: { orderId in path = [.order(orderId)] },
                            onManageAddresses: { path = [] },
                            onSessionExpired: { path = [] },
                        )
                    case .auth:
                        LoginView(onLoginSuccess: { path = [] })
                    case .register:
                        RegisterView(onRegisterSuccess: { path = [] })
                    case .oauth:
                        OAuthView(onOAuthSuccess: { path = [] })
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
    let onOpenOrders: () -> Void

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
                // HRD-303: the bell is the notification entry point, so it carries an explicit
                // accessible name including the unread badge (WCAG 4.1.2 / TalkBack & VoiceOver).
                .accessibilityLabel(unreadCount > 0 ? "Notifications, \(unreadCount) unread" : "Notifications")
                .accessibilityHint("Opens the notification center")
                Spacer()
                Button {
                    onOpenOrders()
                } label: {
                    Image(systemName: "bag")
                        .font(.subheadline)
                        .foregroundColor(.primary)
                }
                .accessibilityLabel("My orders")
                .accessibilityHint("Opens the orders list")
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
                .font(.headline)
                .foregroundColor(.orange)
            Text("Stay notified about meal plan reminders and order updates.")
                .font(.headline)
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
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