import SwiftUI
import Shared

/// The in-app notification center (NTF-507): the user's notifications, most recent first, with
/// read/unread state, mark-as-read on tap, pull-to-refresh, and the loading / error / empty states.
///
/// Backed by the shared `NotificationsViewModel` -- the same one the Compose screen (NTF-506)
/// uses -- so both platforms render one behaviour. The screen reads the view model's current state
/// through `currentState()` after each mutation and keeps it in `@State`, which is what makes
/// SwiftUI re-render on load / refresh / mark-read.
struct NotificationsView: View {
    @StateObject private var viewModel: NotificationsViewModel = createNotificationsViewModel()
    @State private var state: NotificationsUiState?
    let onClose: () -> Void
    let onOpenPreferences: () -> Void

    init(
        onClose: @escaping () -> Void,
        onOpenPreferences: @escaping () -> Void = {},
    ) {
        self.onClose = onClose
        self.onOpenPreferences = onOpenPreferences
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Notifications")
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                Button {
                    onOpenPreferences()
                } label: {
                    Image(systemName: "gearshape")
                        .font(.subheadline)
                        .foregroundColor(.primary)
                }
                .accessibilityLabel("Notification preferences")
                .accessibilityHint("Opens notification preferences")
                Button("Done") {
                    onClose()
                }
            }
            .padding()

            ScrollView {
                VStack(spacing: 8) {
                    if let state = state {
                        if state.isLoading && state.notifications.isEmpty {
                            loadingView
                        } else if state.error != nil, state.notifications.isEmpty {
                            errorView { Task { await load() } }
                        } else if state.notifications.isEmpty {
                            emptyView
                        } else {
                            ForEach(state.notifications.indices, id: \.self) { index in
                                Button {
                                    Task { await markAsRead(state.notifications[index].id) }
                                } label: {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(state.notifications[index].title)
                                            .font(.subheadline)
                                            .foregroundColor(
                                                state.notifications[index].isRead ? .secondary : .primary
                                            )
                                        Text(state.notifications[index].body)
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                .buttonStyle(.borderless)
                                // HRD-303: name each notification from its text content so screen readers
                                // announce the title + body (WCAG 4.1.2).
                                .accessibilityLabel("\(state.notifications[index].title) \(state.notifications[index].body)")
                            }
                        }
                    }
                }
            }
            .refreshable {
                await refresh()
            }
            .task {
                await load()
            }
        }
    }

    // MARK: - views

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading your notifications…")
                // HRD-303: announce the loading state to screen readers via a polite live region
                // (WCAG 4.1.3).
                .accessibilityLiveRegion(.polite)
        }
    }

    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "bell.slash")
                .font(.title)
            Text("No notifications yet.")
        }
    }

    private func errorView(retry: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "bell.slash")
                .font(.title)
            Text("Couldn't load your notifications.")
                // HRD-303: announce errors through a polite live region so screen readers read them
                // when they appear (WCAG 3.3.1 / 4.1.3).
                .accessibilityLiveRegion(.polite)
            Button("Retry") {
                retry()
            }
        }
    }

    // MARK: - actions

    private func load() async {
        await viewModel.load()
        state = viewModel.currentState()
    }

    private func refresh() async {
        await viewModel.refresh()
        state = viewModel.currentState()
    }

    private func markAsRead(_ id: String) async {
        await viewModel.markAsRead(id)
        state = viewModel.currentState()
    }
}

#Preview {
    NotificationsView(onClose: {})
}