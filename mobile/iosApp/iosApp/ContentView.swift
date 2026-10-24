import SwiftUI
import Shared
import UIKit
import UserNotifications

private let greeting = Greeting().greet()

struct ContentView: View {
    @State private var authorizationStatus: UNNotificationSettings.AuthorizationStatus = .notDetermined
    @State private var hasRequested = false
    @State private var showingNotifications = false

    init() {
        // NTF-504: the manager reports the authorization status back into the UI.
        PushNotificationManager.shared.onAuthorizationChange = { status in
            authorizationStatus = status
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
            } else if showingNotifications {
                NotificationsView(onClose: { showingNotifications = false })
            } else {
                HomeContent(onOpenNotifications: { showingNotifications = true })
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