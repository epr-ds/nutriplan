# Notification Service

**Bounded context:** Notification. Push notifications (FCM/APNs), order-status events, and
plan reminders, driven by domain events over the message bus.

- **Datastore:** Redis
- **Consumes:** order lifecycle events from Commerce; plan events from Dietary.

> ⚙️ **Framework TBD (Phase 0 ADR).** Implemented in Phase 5.
