import SwiftUI
import Shared

@main
struct NutriPlanApp: App {
    init() {
        // Initialize Koin and HttpClient for iOS
        KoinInitializerKt.doInitKoin()
        HttpClientFactoryKt.initHttpClient()
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
