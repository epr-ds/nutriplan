import SwiftUI
import Shared
import UIKit
import UserNotifications

struct ContentView: View {
    @State private var authorizationStatus: UNNotificationSettings.AuthorizationStatus = .notDetermined
    @State private var hasRequested = false

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
            } else {
                Text(greeting)
                    .padding()
            }
        }
    }

    private let greeting = Greeting().greet()
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