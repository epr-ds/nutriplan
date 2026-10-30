import SwiftUI
import Shared
import Foundation

/// The OAuth sign-in screen (IDN-506): one button per provider the current platform can present, the
/// in-flight consent state, and the error. Backed by the shared `OAuthViewModel` -- the same one the
/// Compose OAuth screen (IDN-505) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on tap / consent / retry.
struct OAuthView: View {
    @StateObject private var viewModel: OAuthViewModel = createOAuthViewModel()
    @State private var state: OAuthUiState?

    let onOAuthSuccess: () -> Void

    init(onOAuthSuccess: @escaping () -> Void = {}) {
        self.onOAuthSuccess = onOAuthSuccess
    }

    var body: some View {
        VStack(spacing: 16) {
            Text("Sign in with a provider")
                .font(.title)
                .accessibilityAddTraits(.isHeader)

            ForEach(providers, id: \.self) { provider in
                Button {
                    Task { if await viewModel.signIn(provider) { onOAuthSuccess() } }
                } label: { Text(buttonTitle(for: provider)) }
                .disabled(state?.isLoading ?? false)
            }

            if let error = state?.error {
                errorBanner(error: error) {
                    if let provider = viewModel.supportedProviders.first {
                        Task { _ = await viewModel.signIn(provider) }
                    }
                }
            }
        }
        .padding()
    }

    // MARK: - building blocks

    private var providers: [OAuthProvider] {
        Array(viewModel.supportedProviders).sorted { $0.slug < $1.slug }
    }

    private func errorBanner(error: AuthError, retry: @escaping () -> Void) -> some View {
        HStack {
            Text(errorText(error))
                .font(.subheadline)
                .foregroundColor(.error)
            Button("Retry") { retry() }
        }
    }

    private func buttonTitle(for provider: OAuthProvider) -> String {
        switch provider {
        case .GOOGLE: return "Continue with Google"
        case .FACEBOOK: return "Continue with Facebook"
        case .APPLE: return "Continue with Apple"
        }
    }

    private func errorText(_ error: AuthError) -> String {
        switch error {
        case .INVALID_CREDENTIALS: return "Sign-in was rejected. Please try again."
        case .TOO_MANY_ATTEMPTS: return "Too many attempts. Please wait a moment and try again."
        case .SERVER_PROBLEM: return "The service could not process the request. Try again."
        case .LOGIN_FAILED: return "The sign-in failed. Please try again."
        case .NETWORK: return "Could not reach the service. Check your connection and try again."
        case .UNKNOWN: return "Something went wrong. Please try again."
        }
    }
}

#Preview {
    OAuthView()
}