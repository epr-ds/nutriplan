"""Payment provider abstraction and its adapters (COM-201).

A single :class:`~app.payments.provider.PaymentProvider` port fronts every payment backend
(Stripe/Conekta today, more later); the concrete provider is chosen from configuration by
:func:`~app.payments.factory.build_payment_provider`. Everything above the port speaks the
provider-agnostic vocabulary in :mod:`app.domain.payment`, so swapping providers changes nothing
else and no layer imports a payment SDK directly.
"""
