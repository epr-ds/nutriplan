import UIKit
import UserNotifications

/// Native APNs push setup (NTF-503): token registration plus `UNUserNotificationCenter`
/// foreground/background handling for the iOS app.
///
/// The UIKit side owns what APNs requires: registering the device through `UIApplication` and
/// presenting or deferring delivered notifications. The shared KMP layer owns the backend side
/// (NTF-501: `NotificationRepository.registerDevice(platform:token:)`); the callbacks below are the
/// app-side sink for the token and for taps, so the app can register the token and resolve deep
/// links without the push layer knowing about the data layer.
final class PushNotificationManager: NSObject, UNUserNotificationCenterDelegate {

    /// Shared instance; the app delegate points the notification center at it and registers.
    static let shared = PushNotificationManager()

    /// Invoked with the APNs device token once `UIApplication` hands it over; the app registers it
    /// with the backend through the shared notification repository.
    var onDeviceToken: ((String) -> Void)?

    /// Invoked when APNs registration failed; the backend keeps the token stale and retries later.
    var onDeviceTokenError: ((Error) -> Void)?

    /// Invoked when the user taps a delivered notification; carries the payload key the
    /// notification service attached (`deepLink` for order/plan/meal deep links, NTF-304).
    var onNotificationTap: ((String?) -> Void)?

    override init() {
        super.init()
    }

    /// Ask `UIApplication` to register for remote notifications (APNs).
    func registerForRemoteNotifications() {
        UIApplication.shared.registerForRemoteNotifications()
    }

    /// Hand a device token received from `UIApplication` to the app.
    func handleDeviceToken(_ deviceToken: Data) {
        let token = UUID(uuidBytes: deviceToken)?.uuidString ?? ""
        onDeviceToken?(token)
    }

    /// Hand an APNs registration failure to the app.
    func handleRegistrationError(_ error: Error) {
        onDeviceTokenError?(error)
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// Foreground: the notification is on screen; present it. Rich pushes (NTF-405) arrive as
    /// mutable content, so the presentation renders the latest payload for the alert/banner/sound
    /// style the center picks.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.alert, .badge, .sound])
    }

    /// Background: the notification was delivered while the app was not foreground; the user
    /// tapped it, so resolve the deep link from the payload and hand it to the app.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let deepLink = response.notification.request.content.userInfo["deepLink"] as? String
        onNotificationTap?(deepLink)
        completionHandler()
    }
}