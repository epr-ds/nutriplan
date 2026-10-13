import SwiftUI
import Shared

@main
struct NutriPlanApp: App {
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
