import SwiftUI
import Foundation
import Shared

/// The notification preferences screen (NTF-509): channel + per-type toggles and quiet hours,
/// backed by the shared [NotificationsViewModel]; updates optimistically and roll back on failure.
struct NotificationsPreferencesView: View {
    @StateObject private var viewModel: NotificationsViewModel = createNotificationsViewModel()
    @State private var preferences: NotificationPreferences?
    @State private var time = Date()

    let onBack: () -> Void

    init(onBack: @escaping () -> Void) {
        self.onBack = onBack
    }

    var body: some View {
        List {
            Toggle(
                "Push notifications",
                isOn: Binding(
                    get: { preferences?.pushEnabled ?? false },
                    set: { viewModel.updatePushEnabled(enabled: $0) },
                ),
            )

            Toggle(
                "Meal plan reminders",
                isOn: Binding(
                    get: { preferences?.mealReminders ?? false },
                    set: { viewModel.updateMealReminders(enabled: $0) },
                ),
            )
            .disabled(!(preferences?.pushEnabled ?? false))

            Toggle(
                "Order updates",
                isOn: Binding(
                    get: { preferences?.orderUpdates ?? false },
                    set: { viewModel.updateOrderUpdates(enabled: $0) },
                ),
            )
            .disabled(!(preferences?.pushEnabled ?? false))

            Toggle(
                "Promotions",
                isOn: Binding(
                    get: { preferences?.promotions ?? false },
                    set: { viewModel.updatePromotions(enabled: $0) },
                ),
            )
            .disabled(!(preferences?.pushEnabled ?? false))

            Toggle(
                "Email notifications",
                isOn: Binding(
                    get: { preferences?.emailEnabled ?? false },
                    set: { viewModel.updateEmailEnabled(enabled: $0) },
                ),
            )

            Text("Quiet hours")
                .font(.headline)

            DatePicker(
                "Time",
                selection: $time,
                displayedComponents: [.hour, .minute],
            )
            .onChange(of: time) { _ in
                let start = String(format: "%02d:%02d", Calendar.current.component(.hour, from: time),
                                   Calendar.current.component(.minute, from: time))
                let end = String(format: "%02d:%02d", Calendar.current.component(.hour, from: time),
                                 Calendar.current.component(.minute, from: time))
                viewModel.updateQuietHours(start: start, end: end)
            }
        }
        .onAppear {
            Task { await viewModel.loadPreferences() }
        }
        .navigationBarBackButtonDisabled(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button("Back") { onBack() }
            }
        }
    }
}

#Preview {
    NotificationsPreferencesView(onBack: {})
}