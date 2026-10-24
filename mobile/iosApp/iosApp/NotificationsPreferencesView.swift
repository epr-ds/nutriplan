import SwiftUI
import Foundation
import Shared

/// The notification preferences screen (NTF-509): channel + per-type toggles and quiet hours,
/// backed by the shared [NotificationsViewModel]; updates optimistically and roll back on failure.
struct NotificationsPreferencesView: View {
    @StateObject private var viewModel: NotificationsViewModel = createNotificationsViewModel()
    @State private var preferences: NotificationPreferences?
    @State private var startTime = Date()
    @State private var endTime = Date()

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
                    set: { newValue in
                        Task { await viewModel.updatePushEnabled(enabled: newValue) }
                    },
                ),
            )

            Toggle(
                "Meal plan reminders",
                isOn: Binding(
                    get: { preferences?.mealReminders ?? false },
                    set: { newValue in
                        Task { await viewModel.updateMealReminders(enabled: newValue) }
                    },
                ),
            )
            .disabled(!(preferences?.pushEnabled ?? false))

            Toggle(
                "Order updates",
                isOn: Binding(
                    get: { preferences?.orderUpdates ?? false },
                    set: { newValue in
                        Task { await viewModel.updateOrderUpdates(enabled: newValue) }
                    },
                ),
            )
            .disabled(!(preferences?.pushEnabled ?? false))

            Toggle(
                "Promotions",
                isOn: Binding(
                    get: { preferences?.promotions ?? false },
                    set: { newValue in
                        Task { await viewModel.updatePromotions(enabled: newValue) }
                    },
                ),
            )
            .disabled(!(preferences?.pushEnabled ?? false))

            Toggle(
                "Email notifications",
                isOn: Binding(
                    get: { preferences?.emailEnabled ?? false },
                    set: { newValue in
                        Task { await viewModel.updateEmailEnabled(enabled: newValue) }
                    },
                ),
            )

            Text("Quiet hours")
                .font(.headline)

            DatePicker(
                "Start",
                selection: $startTime,
                displayedComponents: [.hour, .minute],
            )
            .onChange(of: startTime) { _ in
                Task {
                    await viewModel.updateQuietHours(
                        start: Self.timeComponents(from: startTime),
                        end: Self.timeComponents(from: endTime),
                    )
                }
            }

            DatePicker(
                "End",
                selection: $endTime,
                displayedComponents: [.hour, .minute],
            )
            .onChange(of: endTime) { _ in
                Task {
                    await viewModel.updateQuietHours(
                        start: Self.timeComponents(from: startTime),
                        end: Self.timeComponents(from: endTime),
                    )
                }
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

    private static func timeComponents(from date: Date) -> String {
        let calendar = Calendar.current
        return String(
            format: "%02d:%02d",
            calendar.component(.hour, from: date),
            calendar.component(.minute, from: date),
        )
    }
}

#Preview {
    NotificationsPreferencesView(onBack: {})
}