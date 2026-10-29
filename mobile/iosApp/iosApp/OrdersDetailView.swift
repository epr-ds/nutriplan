import SwiftUI
import Shared
import Foundation

/// The detail of one of the user's orders: its status timeline, items and totals, and where and
/// when it is delivered, plus the cancel affordance. Backed by the shared `OrderDetailViewModel` --
/// the same one the Compose screen (COM-703) uses -- so both platforms render one behaviour.
struct OrderDetailView: View {
    @StateObject private var viewModel: OrderDetailViewModel = createOrderDetailViewModel()
    @State private var state: OrderDetailUiState?

    let orderId: String
    let onBack: () -> Void
    let onRetry: () -> Void
    let onRequestCancel: () -> Void
    let onConfirmCancel: () -> Void
    let onDismissCancel: () -> Void
    let onDismissCancelError: () -> Void
    let onSessionExpired: () -> Void

    init(
        orderId: String,
        onBack: @escaping () -> Void = {},
        onRetry: @escaping () -> Void = {},
        onRequestCancel: @escaping () -> Void = {},
        onConfirmCancel: @escaping () -> Void = {},
        onDismissCancel: @escaping () -> Void = {},
        onDismissCancelError: @escaping () -> Void = {},
        onSessionExpired: @escaping () -> Void = {},
    ) {
        self.orderId = orderId
        self.onBack = onBack
        self.onRetry = onRetry
        self.onRequestCancel = onRequestCancel
        self.onConfirmCancel = onConfirmCancel
        self.onDismissCancel = onDismissCancel
        self.onDismissCancelError = onDismissCancelError
        self.onSessionExpired = onSessionExpired
    }

    @ViewBuilder
    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(spacing: 0) {
                    if let state = state {
                        if state.loadError != nil && state.order == nil {
                            errorView { onRetry() }
                        } else if state.order == nil {
                            loadingView
                        } else if let order = state.order {
                            detail(order: order, state: state)
                        }
                    }
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
        .confirmationDialog(
            Text("Cancel this order?"),
            isPresented: Binding(
                get: { state?.confirmingCancel ?? false },
                set: { if !$0 { onDismissCancel() } },
            ),
            titleVisibility: .visible,
        ) {
            Button("Cancel order") { onConfirmCancel() }
            Button("Keep order") { onDismissCancel() }
        } message: {
            Text("It won't be prepared or delivered. If you already paid, you'll get a refund.")
        }
    }

    // MARK: - views

    private var header: some View {
        HStack {
            Button(action: onBack) {
                Image(systemName: "chevron.left")
                    .font(.subheadline)
                    .foregroundColor(.primary)
            }
            .accessibilityLabel("Back")

            Text("Order details")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            Spacer()
        }
        .padding()
    }

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading the order")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(retry: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
            Text("Couldn't load this order.")
                .accessibilityLiveRegion(.polite)
            Button("Retry") { retry() }
        }
    }

    @ViewBuilder
    private func detail(order: Order, state: OrderDetailUiState) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Text(orderTitle(order))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                StatusChip(status: order.status)
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)

            if let refreshError = state.refreshError {
                Text("Showing your saved copy of this order. It may be out of date.")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 16)
                    .accessibilityLiveRegion(.polite)
            }

            if let cancelError = state.cancelError {
                HStack(spacing: 8) {
                    Text(cancelErrorText(cancelError))
                        .font(.subheadline)
                        .foregroundColor(.error)
                        .padding(.leading, 16)
                        .padding(.trailing, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Button("Dismiss") { onDismissCancelError() }
                }
                .padding(.vertical, 8)
            }

            sectionHeading("Status")
            timeline(steps: state.timeline)

            sectionHeading("Items")
            items(order: order)

            delivery(order: order, state: state)

            if state.canCancel {
                Button("Cancel order") { onRequestCancel() }
                    .padding(.horizontal, 16)
            }
            if state.isCancelling {
                ProgressView()
                    .padding(.horizontal, 16)
            }
        }
    }

    private func sectionHeading(_ title: String) -> some View {
        Text(title)
            .font(.titleMedium)
            .accessibilityAddTraits(.isHeader)
    }

    // MARK: - actions

    private func load() async {
        await viewModel.load(orderId)
        let current = viewModel.currentState()
        state = current
        if current.sessionExpired { onSessionExpired() }
    }
}

// MARK: - sub-views

private struct StatusChip: View {
    let status: String?

    var body: some View {
        Text(statusText(status))
            .font(.caption2)
            .fontWeight(.semibold)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(statusColor(status).opacity(0.25))
            .foregroundColor(statusColor(status))
            .clipShape(Capsule())
    }

    private func statusText(_ status: String?) -> String {
        guard let status else { return "Unknown" }
        switch status {
        case "pending":
            return "Pending"
        case "confirmed", "preparing", "in_transit":
            return "Active"
        case "delivered":
            return "Delivered"
        case "cancelled":
            return "Cancelled"
        default:
            return "Unknown"
        }
    }

    private func statusColor(_ status: String?) -> Color {
        guard let status else { return .secondary }
        switch status {
        case "pending":
            return .orange
        case "confirmed", "preparing", "in_transit":
            return .blue
        case "delivered":
            return .green
        case "cancelled":
            return .red
        default:
            return .secondary
        }
    }
}

private struct TimelineRow: View {
    let step: TimelineStep

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(timelineDotColor(step.state))
                .frame(width: 12, height: 12)
            VStack(alignment: .leading, spacing: 2) {
                Text(statusText(step.status))
                Text(timelineStateText(step.state))
                if let reachedAt = step.reachedAt {
                    Text(reachedAt)
                }
            }
        }
    }

    private func timelineDotColor(_ state: TimelineStepState) -> Color {
        switch state {
        case .DONE:
            return .blue
        case .CURRENT:
            return .blue
        case .UPCOMING:
            return .secondary
        }
    }

    private func timelineStateText(_ state: TimelineStepState) -> String {
        switch state {
        case .DONE:
            return "done"
        case .CURRENT:
            return "current step"
        case .UPCOMING:
            return "upcoming"
        }
    }

    private func statusText(_ status: String?) -> String {
        guard let status else { return "Unknown" }
        switch status {
        case "pending":
            return "Pending"
        case "confirmed", "preparing", "in_transit":
            return "Active"
        case "delivered":
            return "Delivered"
        case "cancelled":
            return "Cancelled"
        default:
            return "Unknown"
        }
    }
}

// MARK: - sub-views

private extension OrderDetailView {
    @ViewBuilder
    func timeline(steps: List<TimelineStep>) -> some View {
        VStack(spacing: 0) {
            ForEach(steps.indices, id: \.self) { index in
                if let step = steps[index] {
                    TimelineRow(step: step)
                }
            }
        }
    }

    @ViewBuilder
    func items(order: Order) -> some View {
        VStack(spacing: 4) {
            ForEach(order.items.indices, id: \.self) { index in
                if let line = order.items[index] {
                    HStack(spacing: 8) {
                        Text("\(line.name ?? "") × \(line.quantity ?? 0)")
                        Spacer()
                        Text(moneyText(line.lineTotal))
                    }
                }
            }

            VStack(spacing: 4) {
                Text("Subtotal")
                Text(moneyText(order.subtotal))
                Text("Delivery")
                Text(moneyText(order.deliveryFee))
                Text("Total: \(moneyText(order.total))")
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }
        }
    }

    @ViewBuilder
    func delivery(order: Order, state: OrderDetailUiState) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let kind = order.fulfillmentType {
                Text(kindLabel(kind))
            }
            if let store = order.provider?.name ?? order.provider?.id {
                Text("From \(store)")
            }
            if let deliveryDate = order.deliveryDate {
                Text(listOfNotNil(formatPlanDay(deliveryDate), order.deliveryTimeSlot))
            }
            if let trackingUrl = order.trackingUrl, !trackingUrl.isEmpty {
                Text(trackingUrl)
            }
            if let estimatedDelivery = order.estimatedDelivery {
                Text(formatOrderTime(estimatedDelivery))
            }
            if let refund = order.refund {
                Text(refund.refundId ?: refund.status ?: "refund")
            }
            if let address = order.deliveryAddress {
                addressLines(address).forEach { Text($0) }
                if let instructions = address.instructions, !instructions.isEmpty {
                    Text(instructions)
                }
            }
        }
    }
}

// MARK: - helpers

private func cancelErrorText(_ error: OrderError) -> String {
    switch error {
    case .NETWORK:
        return "Could not cancel the order right now. Try again."
    case .SERVER_PROBLEM:
        return "The service could not process the cancellation. Try again."
    case .SESSION_EXPIRED:
        return "Sign in again to cancel this order."
    case .NOT_FOUND:
        return "This order is no longer available."
    case .CONFLICT:
        return "This order can no longer be cancelled."
    case .PAYMENT_DECLINED:
        return "The cancellation could not be confirmed."
    case .REJECTED:
        return "The cancellation was rejected."
    case .UNKNOWN:
        return "The cancellation failed."
    }
}

private func moneyText(_ money: Money?) -> String {
    if let formatted = money?.formatted {
        return formatted
    }
    if let amount = money?.amount {
        return String(format: "%.2f", amount)
    }
    return ""
}

private func formatPlanDay(_ iso: String) -> String {
    var result = ""
    result.reserveCapacity(10)
    for character in iso.prefix(10) {
        result.append(character)
    }
    return result
}

private func formatOrderTime(_ iso: String) -> String {
    var raw = ""
    raw.reserveCapacity(19)
    for character in iso.prefix(19) {
        raw.append(character)
    }
    let formatter = DateTimeFormatter()
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
    formatter.timeZone = TimeZone(identifier: "UTC")
    if let date = formatter.date(from: raw) {
        let display = DateFormatter()
        display.dateFormat = "MMM d, h:mm a"
        return display.string(from: date)
    }
    return iso
}

private func kindLabel(_ type: String) -> String {
    switch type {
    case "dark_kitchen":
        return "Dark kitchen"
    case "grocery_delivery":
        return "Grocery delivery"
    case "pickup":
        return "Pickup"
    default:
        return type
    }
}

private func listOfNotNil(_ first: String?, _ second: String?) -> String {
    if let first { return first }
    if let second { return second }
    return ""
}

private func orderTitle(_ order: Order) -> String {
    if let createdAt = order.createdAt {
        return "Placed \(formatPlanDay(createdAt))"
    }
    return "Order"
}

private func addressLines(_ address: OrderAddress) -> [String] {
    var lines: [String] = []
    let parts = [address.street, address.apartment]
        .compactMap { $0 }
        .filter { !$0.isEmpty }
    if !parts.isEmpty {
        lines.append(parts.joined(separator: ", "))
    }
    lines.append("\(address.city), \(address.state) \(address.zipCode)")
    lines.append(address.country)
    return lines
}

#Preview {
    OrderDetailView(orderId: "o1")
}