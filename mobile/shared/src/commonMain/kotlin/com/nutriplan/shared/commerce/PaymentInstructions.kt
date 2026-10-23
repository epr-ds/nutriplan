package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.BankTransfer
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.PaymentApproval
import com.nutriplan.shared.data.model.PaymentVoucher

/**
 * What the user still has to do to pay for an order (COM-507). A card is charged when the order is
 * placed; the other methods leave the order `pending` with instructions, until the provider confirms
 * the payment.
 */
sealed interface PaymentInstructions {
    /** Nothing to do: paid by card, paid already, unpaid on purpose, or cancelled. */
    data object None : PaymentInstructions

    /** Pay the voucher at an OXXO store before it expires. */
    data class PayAtOxxo(val voucher: PaymentVoucher) : PaymentInstructions

    /** Make the SPEI transfer from a bank before it expires. */
    data class TransferWithSpei(val transfer: BankTransfer) : PaymentInstructions

    /** Approve the payment on PayPal before it expires. */
    data class ApproveWithPayPal(val approval: PaymentApproval) : PaymentInstructions
}

/** What is left to pay this order with; only a `pending` order can have anything left to do. */
fun Order.paymentInstructions(): PaymentInstructions {
    if (status != "pending") return PaymentInstructions.None
    voucher?.let { return PaymentInstructions.PayAtOxxo(it) }
    transfer?.let { return PaymentInstructions.TransferWithSpei(it) }
    approval?.let { return PaymentInstructions.ApproveWithPayPal(it) }
    return PaymentInstructions.None
}
