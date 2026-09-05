"""The notification domain: what a notification *is*, independent of how it is stored.

Nothing in this package imports a driver, a framework, or a settings object. The store
adapters (``app.adapters``) depend on these types; these types depend on nothing, which is
what lets the same model back the Redis feed today and anything else later.
"""
