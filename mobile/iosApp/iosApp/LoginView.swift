import SwiftUI
import Shared
import Foundation

/// The sign-in form (IDN-502): email + password, inline field errors, the form-level error, and
/// the submit that moves the session on success. Backed by the shared `LoginViewModel` -- the same
/// one the Compose login screen (IDN-501) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on input / submit / retry.
struct LoginView: View {
    @StateObject private var viewModel: LoginViewModel = createLoginViewModel()
    @State private var state: LoginUiState?

    let onLoginSuccess: () -> Void

    init(onLoginSuccess: @escaping () -> Void = {}) {
        self.onLoginSuccess = onLoginSuccess
    }

    var body: some View {
        VStack(spacing: 16) {
            Text("Welcome back")
                .font(.title)
                .accessibilityAddTraits(.isHeader)

            TextField("Email", text: Binding(
                get: { state?.email ?? "" },
                set: { viewModel.onEmailChange($0) }
            ))
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled(true)
            .textContentType(.emailAddress)

            if let emailError = state?.emailError {
                Text(fieldErrorText(emailError))
                    .font(.caption)
                    .foregroundColor(.error)
            }

            SecureField("Password", text: Binding(
                get: { state?.password ?? "" },
                set: { viewModel.onPasswordChange($0) }
            ))

            if let passwordError = state?.passwordError {
                Text(fieldErrorText(passwordError))
                    .font(.caption)
                    .foregroundColor(.error)
            }

            if let error = state?.error {
                errorBanner(error: error) {
                    Task { if await viewModel.submit() { onLoginSuccess() } }
                }
            }

            Button {
                Task { if await viewModel.submit() { onLoginSuccess() } }
            } label: { Text("Sign in") }
            .disabled(state?.isLoading ?? false)
        }
        .padding()
    }

    // MARK: - building blocks

    private func errorBanner(error: AuthError, retry: @escaping () -> Void) -> some View {
        HStack {
            Text(errorText(error))
                .font(.subheadline)
                .foregroundColor(.error)
            Button("Retry") { retry() }
        }
    }

    private func fieldErrorText(_ error: FieldError) -> String {
        switch error {
        case .EMAIL_REQUIRED: return "An email address is required."
        case .EMAIL_INVALID: return "Enter a valid email address."
        case .PASSWORD_REQUIRED: return "A password is required."
        case .PASSWORD_TOO_SHORT: return "The password is too short."
        case .CONFIRM_PASSWORD_REQUIRED: return "Confirm the password."
        case .CONFIRM_PASSWORD_MISMATCH: return "The passwords do not match."
        }
    }

    private func errorText(_ error: AuthError) -> String {
        switch error {
        case .INVALID_CREDENTIALS: return "Incorrect email or password. Please try again."
        case .TOO_MANY_ATTEMPTS: return "Too many attempts. Please wait a moment and try again."
        case .SERVER_PROBLEM: return "The service could not process the request. Try again."
        case .LOGIN_FAILED: return "The sign-in failed. Please try again."
        case .NETWORK: return "Could not reach the service. Check your connection and try again."
        case .UNKNOWN: return "Something went wrong. Please try again."
        }
    }
}

#Preview {
    LoginView()
}