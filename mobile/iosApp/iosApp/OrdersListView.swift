import SwiftUI
import Shared
import Foundation

/// The user's orders, newest first -- each with its status, delivery and total -- filtered by
/// status (all, active, delivered, cancelled), with a reorder action, and the loading / error /
/// empty / filtered-empty states, plus the stale-list note. Backed by the shared `OrderListViewModel`
/// -- the same one the Compose screen from COM-701 uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / refresh / filter change.
struct OrdersListView: View {
    @StateObject private var viewModel: OrderListViewModel = createOrderListViewModel()
    @State private var state: OrderListUiState?

    let onBack: () -> Void
    let onOrderClick: (String) -> Void
    let onReorder: (String) -> Void
    let onBrowsePlans: () -> Void
    let onSessionExpired: () -> Void

    init(
        onBack: @escaping () -> Void,
        onOrderClick: @escaping (String) -> Void = {},
        onReorder: @escaping (String) -> Void = {},
        onBrowsePlans: @escaping () -> Void = {},
        onSessionExpired: @escaping () -> Void = {},
    ) {
        self.onBack = onBack
        self.onOrderClick = onOrderClick
        self.onReorder = onReorder
        self.onBrowsePlans = onBrowsePlans
        self.onSessionExpired = onSessionExpired
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(spacing: 8) {
                    if let state = state {
                        if state.isLoading && state.orders.isEmpty {
                            loadingView
                        } else if state.loadError != nil && state.orders.isEmpty {
                            errorView { Task { await load() } }
                        } else if state.isEmpty {
                            emptyView
                        } else if state.isFilteredEmpty {
                            filteredEmptyView
                        } else {
                            orderList
                        }
                    }
                }
            }
            .refreshable { await refresh() }
            .task { await load() }
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

            Text("Orders")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            Spacer()
        }
        .padding()
    }

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading your orders…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(retry: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
            Text("Couldn't load your orders.")
                .accessibilityLiveRegion(.polite)
            Button("Retry") { retry() }
        }
    }

    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "bag.slash")
            Text("No orders yet.")
            Button("Browse meal plans") { onBrowsePlans() }
        }
    }

    private var filteredEmptyView: some View {
        Text("No orders with this status.")
            .font(.subheadline)
            .foregroundColor(.secondary)
    }

    private var orderList: some View {
        VStack(spacing: 12) {
            filters
            if let list = state {
                if list.refreshError != nil {
                    Text("Showing your saved orders. They may be out of date.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                ForEach(list.visibleOrders.indices, id: \.self) { index in
                    if let order = list.visibleOrders[index] {
                        OrderRow(
                            order: order,
                            canReorder: viewModel.canReorder(order),
                            onOrderClick: onOrderClick,
                            onReorder: onReorder,
                        )
                    }
                }
            }
        }
    }

    private var filters: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                FilterChip(
                    title: "All",
                    count: state?.count(.ALL) ?? 0,
                    isSelected: isSelected(.ALL),
                    action: { viewModel.selectFilter(.ALL) },
                )
                FilterChip(
                    title: "Active",
                    count: state?.count(.ACTIVE) ?? 0,
                    isSelected: isSelected(.ACTIVE),
                    action: { viewModel.selectFilter(.ACTIVE) },
                )
                FilterChip(
                    title: "Delivered",
                    count: state?.count(.DELIVERED) ?? 0,
                    isSelected: isSelected(.DELIVERED),
                    action: { viewModel.selectFilter(.DELIVERED) },
                )
                FilterChip(
                    title: "Cancelled",
                    count: state?.count(.CANCELLED) ?? 0,
                    isSelected: isSelected(.CANCELLED),
                    action: { viewModel.selectFilter(.CANCELLED) },
                )
            }
            .padding(horizontal: 16, vertical: 8)
        }
    }
}

// MARK: - sub-views

private struct OrderRow: View {
    let order: Order
    let canReorder: Bool
    let onOrderClick: (String) -> Void
    let onReorder: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(orderTitle(order))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                StatusChip(status: order.status)
            }
            Text(orderDeliveryText(order))
                .font(.caption)
                .foregroundColor(.secondary)
            if let itemsSummary = orderItemsSummary(order) {
                Text(itemsSummary)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            HStack(spacing: 8) {
                Text(orderTotalText(order))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if canReorder {
                    Button(action: { onReorder(order.id) }) {
                        Text("Reorder")
                    }
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color(.systemBackground)))
        .onTapGesture { onOrderClick(order.id) }
    }

    private func orderTitle(_ order: Order) -> String {
        if let createdAt = order.createdAt, let day = planDay(createdAt) { return "Placed \(day)" }
        return "Order"
    }

    private func planDay(_ iso: String) -> String { String(iso.prefix(10)) }

    private func orderDeliveryText(_ order: Order) -> String {
        var parts: [String] = []
        if let fulfillmentType = order.fulfillmentType { parts.append(fulfillmentLabel(fulfillmentType)) }
        if let deliveryDate = order.deliveryDate { parts.append(deliveryDate) }
        return parts.joined(separator: ", ")
    }

    private func fulfillmentLabel(_ type: String) -> String {
        switch type {
        case "dark_kitchen": return "Dark kitchen"
        case "grocery_delivery": return "Grocery delivery"
        case "pickup": return "Pickup"
        default: return type
        }
    }

    private func orderItemsSummary(_ order: Order) -> String? {
        let names = order.items.compactMap { $0.name }.filter { !$0.isEmpty }
        guard let first = names.first else { return nil }
        return names.count == 1 ? first : "\(first) and \(names.count - 1) more"
    }

    private func orderTotalText(_ order: Order) -> String {
        if let formatted = order.total?.formatted { return formatted }
        if let amount = order.total?.amount { return String(format: "%.2f", amount) }
        return ""
    }
}

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
        switch status {
        case "pending": return "Pending"
        case "confirmed", "preparing", "in_transit": return "Active"
        case "delivered": return "Delivered"
        case "cancelled": return "Cancelled"
        default: return "Unknown"
        }
    }

    private func statusColor(_ status: String?) -> Color {
        switch status {
        case "pending": return .orange
        case "confirmed", "preparing", "in_transit": return .blue
        case "delivered": return .green
        case "cancelled": return .red
        default: return .secondary
        }
    }
}

private struct FilterChip: View {
    let title: String
    let count: Int
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text("\(title) (\(count))")
                .font(.subheadline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.blue.opacity(0.2) : Color(.systemBackground))
                .clipShape(Capsule())
        }
        .buttonStyle(.borderless)
    }
}

// MARK: - actions

private extension OrdersListView {
    func isSelected(_ filter: OrderFilter) -> Bool {
        guard let state = state else { return false }
        switch state.filter {
        case .ALL: return filter == .ALL
        case .ACTIVE: return filter == .ACTIVE
        case .DELIVERED: return filter == .DELIVERED
        case .CANCELLED: return filter == .CANCELLED
        }
    }

    func load() async {
        await viewModel.load()
        state = viewModel.currentState()
    }

    func refresh() async {
        await viewModel.refresh()
        state = viewModel.currentState()
    }
}

#Preview {
    OrdersListView(onBack: {})
}