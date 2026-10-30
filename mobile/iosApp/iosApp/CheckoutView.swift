import SwiftUI
import Shared
import Foundation

/// The checkout flow: plan, fulfillment, delivery address, day and time slot, review with the
/// itemized price, paying and the confirmation. Backed by the shared `CheckoutViewModel` -- the
/// same one the Compose checkout screen (COM-605) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / refresh / choice change.
struct CheckoutView: View {
    @StateObject private var viewModel: CheckoutViewModel = createCheckoutViewModel()
    @State private var state: CheckoutUiState?

    let planId: String?
    let reorderOrderId: String?
    let onBack: () -> Void
    let onOrderPlaced: (String) -> Void
    let onManageAddresses: () -> Void
    let onSessionExpired: () -> Void

    init(
        planId: String? = nil,
        reorderOrderId: String? = nil,
        onBack: @escaping () -> Void = {},
        onOrderPlaced: @escaping (String) -> Void = { _ in },
        onManageAddresses: @escaping () -> Void = {},
        onSessionExpired: @escaping () -> Void = {},
    ) {
        self.planId = planId
        self.reorderOrderId = reorderOrderId
        self.onBack = onBack
        self.onOrderPlaced = onOrderPlaced
        self.onManageAddresses = onManageAddresses
        self.onSessionExpired = onSessionExpired
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(spacing: 8) {
                    if let state = state {
                        if let order = state.placedOrder {
                            confirmation(order: order, onViewOrder: { onOrderPlaced(order.id) }, onDone: onBack)
                        } else {
                            stepContent(state)
                        }
                    }
                }
            }
            .refreshable { await load() }
            .task { await load() }
            footer
        }
    }

    // MARK: - state

    private func load() async {
        await viewModel.start(state?.deliveryDate ?? "", planId, reorderOrderId)
        let current = viewModel.currentState()
        state = current
        if current.sessionExpired { onSessionExpired() }
    }

    /// The retry of the error banner: the slot / quote / placement the screen is on, or the start
    /// over when the user is still on an earlier step.
    private func retryCheckout() async {
        let current = viewModel.currentState()
        if current.step == .SLOT {
            await viewModel.loadSlots()
        } else if current.step == .REVIEW && current.quote != nil {
            await viewModel.placeOrder()
        } else if current.step == .REVIEW {
            await viewModel.loadQuote()
        } else {
            await viewModel.start(state?.deliveryDate ?? "", planId, reorderOrderId)
        }
    }

    // MARK: - views

    private var header: some View {
        VStack(spacing: 4) {
            HStack {
                Button(action: onBack) {
                    Image(systemName: "chevron.left")
                        .font(.subheadline)
                        .foregroundColor(.primary)
                }
                .accessibilityLabel("Back")

                Text("Checkout")
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)

                Spacer()
            }
            Text(stepProgress)
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .padding()
    }

    private var footer: some View {
        VStack(spacing: 12) {
            if let state = state, state.placedOrder == nil {
                if state.step == .REVIEW {
                    Button(action: {
                        Task { _ = await viewModel.placeOrder() }
                    }) { Text("Place order") }
                    .disabled(state.quote == nil || state.isPlacing)
                } else {
                    Button(action: {
                        Task { _ = await viewModel.next() }
                    }) { Text("Next") }
                }
                if state.step != .PLAN {
                    Button(action: onBack) { Text("Back") }
                }
            }
        }
        .padding()
    }

    @ViewBuilder
    private func stepContent(_ state: CheckoutUiState) -> some View {
        VStack(spacing: 12) {
            Text(stepTitle(state.step))
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            if let error = state.error {
                errorBanner(error: error) { Task { await retryCheckout() } }
            }
            if let problem = state.stepError {
                Text(stepErrorText(problem))
                    .font(.bodyMedium)
                    .foregroundColor(.red)
            }

            if state.step == .PLAN { planStep(state) }
            else if state.step == .FULFILLMENT { fulfillmentStep(state) }
            else if state.step == .ADDRESS { addressStep(state) }
            else if state.step == .SLOT { slotStep(state) }
            else if state.step == .REVIEW { reviewStep(state) }
        }
    }

    // --- steps ---

    private func planStep(_ state: CheckoutUiState) -> some View {
        VStack(spacing: 8) {
            if state.plansLoading {
                loadingView
            } else if state.plans.isEmpty {
                emptyView(title: "No meal plans yet.", description: "Create a meal plan to start an order.")
            } else {
                ForEach(state.plans.indices, id: \.self) { index in
                    planOption(
                        state.plans[index],
                        selected: state.plans[index].id == state.planId,
                    ) { selectPlan(state.plans[index].id) }
                }
            }
        }
    }

    private func fulfillmentStep(_ state: CheckoutUiState) -> some View {
        VStack(spacing: 8) {
            fulfillmentOption(
                "dark_kitchen",
                subtitle: "Cooks your plan fresh",
                selected: state.fulfillmentType == "dark_kitchen",
            ) { selectFulfillment("dark_kitchen") }
            fulfillmentOption(
                "grocery_delivery",
                subtitle: "Delivers from a local store",
                selected: state.fulfillmentType == "grocery_delivery",
            ) { selectFulfillment("grocery_delivery") }
            fulfillmentOption(
                "pickup",
                subtitle: "Pick up at the store",
                selected: state.fulfillmentType == "pickup",
            ) { selectFulfillment("pickup") }

            if state.fulfillmentType == "grocery_delivery" {
                if state.providersLoading {
                    loadingView
                } else if state.providers.isEmpty {
                    Text("No grocery store is offering delivery right now.")
                } else {
                    VStack(spacing: 8) {
                        ForEach(state.providers.indices, id: \.self) { index in
                            providerOption(state.providers[index], selected: state.providers[index].id == state.providerId) { selectProvider(state.providers[index].id ?? "") }
                        }
                    }
                }
            }
        }
    }

    private func addressStep(_ state: CheckoutUiState) -> some View {
        VStack(spacing: 8) {
            if state.addresses.isEmpty {
                VStack(spacing: 8) {
                    emptyView(title: "No saved addresses.", description: "Add a delivery address to continue.")
                    Button("Add address") { onManageAddresses() }
                }
            } else {
                ForEach(state.addresses.indices, id: \.self) { index in
                    savedAddressOption(
                        state.addresses[index],
                        selected: state.addresses[index].id == state.addressId,
                    ) { viewModel.selectAddress(state.addresses[index].id) }
                }
                Button("Manage addresses") { onManageAddresses() }
            }
        }
    }

    private func slotStep(_ state: CheckoutUiState) -> some View {
        VStack(spacing: 12) {
            Text("Delivery day")
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            HStack(spacing: 8) {
                dayOptions(from: state.deliveryDate).forEach { day in
                    dayChip(day, selected: day == state.deliveryDate) { selectDay(day) }
                }
            }

            Text("Delivery time")
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            if state.slotsLoading {
                loadingView
            } else if state.slots.isEmpty {
                Text(stepErrorText(.AREA_NOT_SERVED))
            } else {
                HStack(spacing: 8) {
                    state.slots.forEach { slot in
                        slotChip(slot, selected: slot == state.timeSlot) { selectSlot(slot) }
                    }
                }
            }
        }
    }

    private func reviewStep(_ state: CheckoutUiState) -> some View {
        VStack(spacing: 12) {
            Text("Review")
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            VStack(spacing: 8) {
                summaryRow(state, step: .PLAN) { edit(.PLAN) }
                summaryRow(state, step: .FULFILLMENT) { edit(.FULFILLMENT) }
                summaryRow(state, step: .ADDRESS) { edit(.ADDRESS) }
                summaryRow(state, step: .SLOT) { edit(.SLOT) }
            }

            Text("Price")
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            if state.quoteLoading {
                loadingView
            }
            if let quote = state.quote {
                VStack(spacing: 4) {
                    Divider()
                    priceRow("Subtotal", quote.subtotal)
                    priceRow("Delivery", quote.deliveryFee)
                    priceRow("Total", quote.total, bold: true)
                }
                paymentSection(state)
            }
        }
    }

    // --- paying and the confirmation ---

    private func confirmation(order: Order, onViewOrder: @escaping () -> Void, onDone: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Text(confirmationStatusText(order))
                .font(.bodyLarge)
                .accessibilityAddTraits(.isHeader)
                .accessibilityLiveRegion(.polite)

            if order.status == "pending" {
                instructions(for: order)
            }

            Text("Summary")
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            VStack(spacing: 4) {
                ForEach(order.items.indices, id: \.self) { index in
                    HStack {
                        Text("\(order.items[index].name ?? "") × \(order.items[index].quantity ?? 0)")
                        Spacer()
                        Text(moneyText(order.items[index].lineTotal))
                    }
                }
            }

            VStack(spacing: 4) {
                Divider()
                priceRow("Delivery", order.deliveryFee)
                priceRow("Total", order.total, bold: true)
            }

            Button("Done") { onDone() }
            Button("View order") { onViewOrder() }
        }
    }

    // --- building blocks ---

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading your checkout…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorBanner(error: OrderError, retry: @escaping () -> Void) -> some View {
        HStack {
            Text(errorText(error))
                .font(.bodyMedium)
                .foregroundColor(.red)
            Button("Retry") { retry() }
        }
    }

    private func emptyView(title: String, description: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "bag.slash")
            Text(title)
            Text(description)
        }
    }

    // --- actions ---

    private func selectPlan(_ planId: String) {
        viewModel.selectPlan(planId)
    }

    private func selectFulfillment(_ type: String) {
        Task { await viewModel.selectFulfillment(type) }
    }

    private func selectProvider(_ providerId: String) {
        viewModel.selectProvider(providerId)
    }

    private func selectDay(_ day: String) {
        Task { await viewModel.onDateChange(day) }
    }

    private func selectSlot(_ slot: String) {
        viewModel.selectSlot(slot)
    }

    private func selectPayment(_ type: String) {
        viewModel.selectPayment(type)
    }

    private func saveCardChange(_ save: Bool) {
        viewModel.onSaveCardChange(save)
    }

    private func edit(_ step: CheckoutStep) {
        Task { await viewModel.edit(step) }
    }

    // --- helpers ---

    private var checkoutStepCount: Int { 5 }

    private var stepProgress: String {
        guard let state = state else { return "" }
        return "Step \(stepIndex(state.step)) of \(checkoutStepCount)"
    }

    private func stepTitle(_ step: CheckoutStep) -> String {
        switch step {
        case .PLAN: return "Plan"
        case .FULFILLMENT: return "Fulfillment"
        case .ADDRESS: return "Address"
        case .SLOT: return "Delivery slot"
        case .REVIEW: return "Review"
        }
    }

    private func stepIndex(_ step: CheckoutStep) -> Int {
        switch step {
        case .PLAN: return 1
        case .FULFILLMENT: return 2
        case .ADDRESS: return 3
        case .SLOT: return 4
        case .REVIEW: return 5
        }
    }

    private func stepErrorText(_ error: CheckoutStepError) -> String {
        switch error {
        case .PLAN_REQUIRED: return "Choose a meal plan to continue."
        case .FULFILLMENT_REQUIRED: return "How should it be fulfilled?"
        case .PROVIDER_REQUIRED: return "Choose a store for grocery delivery."
        case .ADDRESS_REQUIRED: return "Choose a delivery address."
        case .DATE_INVALID: return "Choose a delivery day."
        case .SLOT_REQUIRED: return "Choose a delivery time slot."
        case .AREA_NOT_SERVED: return "The dark kitchen does not deliver to this address or day."
        case .PAYMENT_REQUIRED: return "Choose how to pay."
        case .CARD_NOT_VERIFIED: return "The card could not be verified. Try another."
        }
    }

    private func errorText(_ error: OrderError) -> String {
        switch error {
        case .NETWORK: return "Could not reach the service. Try again."
        case .SERVER_PROBLEM: return "The service could not process the request. Try again."
        case .SESSION_EXPIRED: return "Sign in again to continue."
        case .NOT_FOUND: return "This is no longer available."
        case .CONFLICT: return "The order could not be placed now."
        case .PAYMENT_DECLINED: return "The payment was declined. Try another."
        case .REJECTED: return "The payment was rejected."
        case .UNKNOWN: return "Something went wrong. Try again."
        }
    }

    private func fulfillmentTitle(_ type: String) -> String {
        switch type {
        case "dark_kitchen": return "Dark kitchen"
        case "grocery_delivery": return "Grocery delivery"
        default: return "Pickup"
        }
    }

    private func fulfillmentSubtitle(_ type: String) -> String {
        switch type {
        case "dark_kitchen": return "Cooks your plan fresh"
        case "grocery_delivery": return "Delivers from a local store"
        default: return "Pick up at the store"
        }
    }

    private func confirmationStatusText(_ order: Order) -> String {
        guard let status = order.status else { return "Order placed" }
        switch status {
        case "pending": return "Waiting for the payment"
        case "paid": return "Paid"
        case "confirmed", "preparing", "in_transit": return "Active"
        case "delivered": return "Delivered"
        case "cancelled": return "Cancelled"
        default: return "Order placed"
        }
    }

    private func instructions(for order: Order) -> some View {
        VStack(spacing: 8) {
            if let voucher = order.voucher {
                VStack(spacing: 4) {
                    Text("Pay the OXXO voucher of \(moneyText(voucher.amount)) before \(voucher.expiresAt ?? "")")
                    Text("Reference \(voucher.reference ?? "")")
                }
            } else if let transfer = order.transfer {
                VStack(spacing: 4) {
                    Text("Transfer the SPEI amount of \(moneyText(transfer.amount)) to the bank before \(transfer.expiresAt ?? "")")
                    Text("CLABE \(transfer.clabe ?? "") · Reference \(transfer.reference ?? "")")
                }
            } else if let approval = order.approval {
                VStack(spacing: 4) {
                    Text("Approve the PayPal payment before \(approval.expiresAt ?? "")")
                    Text("Reference \(approval.reference ?? "")")
                }
            }
        }
    }

    private func moneyText(_ money: Money?) -> String {
        if let formatted = money?.formatted { return formatted }
        if let amount = money?.amount { return String(format: "%.2f", amount) }
        return ""
    }

    private func formatPlanDay(_ iso: String) -> String { String(iso.prefix(10)) }

    private func dayOptions(from today: String, count: Int = 14) -> [String] {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(identifier: "UTC")
        guard let base = formatter.date(from: today) else { return [] }
        return (0..<count).compactMap { offset in
            guard let date = Calendar(identifier: .gregorian).date(byAdding: .day, value: offset, to: base),
                  let iso = formatter.string(from: date) else { return nil }
            return String(iso.prefix(10))
        }
    }

    private func dayChip(_ day: String, selected: Bool, onClick: @escaping () -> Void) -> some View {
        Button(action: onClick) {
            Text(formatPlanDay(day))
                .font(.subheadline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(selected ? Color.blue.opacity(0.2) : Color(.systemBackground))
                .clipShape(Capsule())
        }
        .buttonStyle(.borderless)
    }

    private func slotChip(_ slot: String, selected: Bool, onClick: @escaping () -> Void) -> some View {
        Button(action: onClick) {
            Text(slot)
                .font(.subheadline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(selected ? Color.blue.opacity(0.2) : Color(.systemBackground))
                .clipShape(Capsule())
        }
        .buttonStyle(.borderless)
    }

    private func planOption(_ plan: MealPlanSummary, selected: Bool, onClick: @escaping () -> Void) -> some View {
        Button(action: onClick) {
            HStack(spacing: 12) {
                optionIndicator(selected: selected)
                VStack(alignment: .leading, spacing: 2) {
                    Text(plan.name).font(.subheadline).fontWeight(.semibold)
                    Text("\(plan.startDate) → \(plan.endDate)").font(.caption).foregroundColor(.secondary)
                }
                Spacer()
            }
        }
    }

    private func fulfillmentOption(_ type: String, subtitle: String?, selected: Bool, onClick: @escaping () -> Void) -> some View {
        Button(action: onClick) {
            HStack(spacing: 12) {
                optionIndicator(selected: selected)
                VStack(alignment: .leading, spacing: 2) {
                    Text(fulfillmentTitle(type)).font(.subheadline).fontWeight(.semibold)
                    Text(subtitle ?? "").font(.caption).foregroundColor(.secondary)
                }
                Spacer()
            }
        }
    }

    private func providerOption(_ provider: FulfillmentProvider, selected: Bool, onClick: @escaping () -> Void) -> some View {
        Button(action: onClick) {
            HStack(spacing: 12) {
                optionIndicator(selected: selected)
                VStack(alignment: .leading, spacing: 2) {
                    Text(provider.name ?? provider.id ?? "")
                    Text(provider.estimatedDelivery ?? "")
                }
                Spacer()
            }
        }
    }

    private func savedAddressOption(_ saved: SavedAddress, selected: Bool, onClick: @escaping () -> Void) -> some View {
        Button(action: onClick) {
            HStack(spacing: 12) {
                optionIndicator(selected: selected)
                VStack(alignment: .leading, spacing: 2) {
                    Text(saved.label ?? saved.address.street).font(.subheadline).fontWeight(.semibold)
                    Text("\(saved.address.zipCode) \(saved.address.city)").font(.caption).foregroundColor(.secondary)
                }
                Spacer()
            }
        }
    }

    private func paymentOption(_ type: String, subtitle: String?, selected: Bool, onClick: @escaping () -> Void) -> some View {
        Button(action: onClick) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(type).font(.subheadline).fontWeight(.semibold)
                    Text(subtitle ?? "").font(.caption).foregroundColor(.secondary)
                }
                Spacer()
                if selected { Image(systemName: "checkmark.circle.fill").foregroundColor(.blue) }
            }
        }
    }

    private func optionIndicator(selected: Bool) -> some View {
        Image(systemName: selected ? "checkmark.circle.fill" : "circle")
            .foregroundColor(selected ? .blue : .secondary)
    }

    private func summaryRow(_ state: CheckoutUiState, step: CheckoutStep, onEdit: @escaping () -> Void) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(stepTitle(step))
                    .font(.labelMedium)
                    .foregroundColor(.secondary)
                Text(summaryValue(state, step: step))
                    .font(.bodyMedium)
            }
            Button(action: onEdit) { Text("Edit") }
        }
    }

    private func summaryValue(_ state: CheckoutUiState, step: CheckoutStep) -> String {
        switch step {
        case .PLAN: return state.plans.first { $0.id == state.planId }?.name ?? ""
        case .FULFILLMENT: {
            let fulfillment = state.fulfillmentType ?? ""
            let provider = state.providers.first { $0.id == state.providerId }?.name ?? ""
            return [fulfillment, provider].filter { !$0.isEmpty }.joined(separator: " · ")
        }
        case .ADDRESS: {
            let address = state.addresses.first { $0.id == state.addressId }?.address
            guard let address else { return "" }
            return "\(address.street), \(address.zipCode) \(address.city)"
        }
        case .SLOT: return "\(formatPlanDay(state.deliveryDate)) · \(state.timeSlot ?? "")"
        case .REVIEW: return ""
        }
    }

    private func priceRow(_ label: String, _ amount: Money?, bold: Bool = false) -> some View {
        HStack {
            Text(label)
                .font(.bodyMedium)
                .fontWeight(bold ? .bold : .regular)
            Spacer()
            Text(moneyText(amount))
                .fontWeight(bold ? .bold : .regular)
        }
    }

    private func paymentSection(_ state: CheckoutUiState) -> some View {
        VStack(spacing: 8) {
            Text("Payment")
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            if state.canPayByCard {
                paymentOption(
                    "credit_card",
                    subtitle: "Pay with a card",
                    selected: state.paymentType == "credit_card",
                ) { selectPayment("credit_card") }
            }
            paymentOption("oxxo", subtitle: "Pay at an OXXO store", selected: state.paymentType == "oxxo") { selectPayment("oxxo") }
            paymentOption("spei", subtitle: "Transfer from a bank", selected: state.paymentType == "spei") { selectPayment("spei") }
            paymentOption("paypal", subtitle: "Approve on PayPal", selected: state.paymentType == "paypal") { selectPayment("paypal") }

            if state.paymentType == "credit_card" {
                HStack {
                    Text("Save this card for the next checkout")
                    Toggle(isOn: Binding(get: { state.saveCard }, set: saveCardChange))
                }
            }
        }
    }
}

#Preview {
    CheckoutView()
}