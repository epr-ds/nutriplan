import SwiftUI
import Shared

struct ContentView: View {
    // Consumes the Kotlin Multiplatform `shared` framework.
    let greeting = Greeting().greet()

    var body: some View {
        Text(greeting)
            .padding()
    }
}

#Preview {
    ContentView()
}
