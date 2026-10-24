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

    /// The authorization status the manager last read (NTF-504): the user has not answered the OS
    /// prompt yet, allowed it, refused it, or accepted quiet/provisional access.
    private(set) var authorizationStatus: UNNotificationSettings.AuthorizationStatus = .notDetermined

    /// Invoked when the authorization status changes (prompt answer or settings change).
    var onAuthorizationChange: ((UNNotificationSettings.AuthorizationStatus) -> Void)?

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

    /// Ask `UIApplication` / `UNUserNotificationCenter` for remote notification authorization
    /// (NTF-504): options are the alert, badge and sound the user was offered; the completion
    /// handler reports the answer (granted / refused) and the error when the request failed.
    func requestAuthorization(
        options: UNNotificationOptions = [.alert, .badge, .sound],
        completionHandler: ((Bool, Error?) -> Void)? = nil,
    ) {
        UNUserNotificationCenter.current().requestAuthorization(options: options) { granted, error in
            if let error = error {
                completionHandler?(false, error)
            } else {
                completionHandler?(granted, nil)
            }
        }
    }

    /// Read the current authorization status (notDetermined / provisional / denied / authorized)
    /// and hand it to the app through [onAuthorizationChange].
    func refreshAuthorizationStatus() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let status = settings.authorizationStatus
            self.authorizationStatus = status
            self.onAuthorizationChange?(status)
        }
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