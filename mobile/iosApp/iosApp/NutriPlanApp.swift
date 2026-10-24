import SwiftUI
import Shared
import UIKit
import UserNotifications

@main
struct NutriPlanApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    init() {
        // Start Koin (with Keychain-backed token storage) and create the shared HTTP client.
        IosBootstrapKt.bootstrapKoin()
        IosBootstrapKt.bootstrapHttpClient()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

/// UIKit lifecycle delegate: points the notification center at the APNs manager and registers the
/// device for remote notifications when the app launches (NTF-503).
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = PushNotificationManager.shared
        PushNotificationManager.shared.refreshAuthorizationStatus()
        PushNotificationManager.shared.registerForRemoteNotifications()
        return true
    }

    func application(
        _ app: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        PushNotificationManager.shared.handleDeviceToken(deviceToken)
    }

    func application(
        _ app: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        PushNotificationManager.shared.handleRegistrationError(error)
    }
}
