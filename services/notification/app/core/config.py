from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.quiet_hours import DEFAULT_TIME_ZONE


class Settings(BaseSettings):
    """Runtime configuration, overridable via NOTIFICATION_-prefixed environment variables.

    12-factor: every value below is environment-driven so the same image runs in dev, CI,
    and production with no code changes. Secrets (push credentials) are injected at runtime
    and typed as ``SecretStr`` so they are masked in logs and reprs, never baked into the
    image.

    The three groups below are the service's dependencies: the Redis datastore, the message
    bus it consumes domain events from, and the push providers it delivers through.
    """

    model_config = SettingsConfigDict(env_prefix="NOTIFICATION_", env_file=".env", extra="ignore")

    app_name: str = "NutriPlan Notification Service"
    environment: str = "development"

    # Datastore (NTF-102). Notifications, read-state, and per-(event, user, type) dedupe keys
    # live in Redis so they are shared across replicas. Leave NOTIFICATION_REDIS_URL blank and
    # the service still starts -- correct for dev/CI, where an in-process store stands in --
    # but it is a hard readiness failure in production. The feed is a rolling window, not an
    # archive: entries age out after ``feed_ttl_seconds``, and a single user's index is capped
    # at ``feed_max_entries`` so one very busy account cannot grow an unbounded sorted set.
    redis_url: str = ""
    redis_namespace: str = "notification"
    feed_ttl_seconds: int = 2_592_000
    feed_max_entries: int = 500

    # Idempotency (NTF-103). A bus redelivers, so "one event, one notification" is enforced
    # here rather than assumed: a handled (event, user, type) triple is remembered for
    # ``dedupe_ttl_seconds``, which must comfortably exceed the bus's realistic redelivery
    # horizon (retries, a pod restart, an NTF-204 dead-letter replay) while staying well
    # under ``feed_ttl_seconds`` -- suppressing a replay on behalf of an original that has
    # already aged out of the feed would leave the user with neither. ``dedupe_claim_seconds``
    # is the short lease held *before* the notification is written; it bounds how long a
    # hard-killed worker can suppress a notification it never actually delivered. Set
    # ``NOTIFICATION_DEDUPE_TTL_SECONDS=0`` to turn deduplication off, which is only sensible
    # when deliberately replaying a fixture stream.
    dedupe_ttl_seconds: int = 86_400
    dedupe_claim_seconds: int = 60

    # Preferences (NTF-104). ``default_time_zone`` is the IANA zone a quiet-hours window is
    # interpreted in when a client does not name one -- a zone *name*, never a fixed offset,
    # so the window keeps meaning "ten at night" across a daylight-saving change instead of
    # silently shifting by an hour twice a year. Preferences themselves are stored without a
    # TTL on purpose (see the Redis adapter): an opt-out that expired would switch itself back
    # on at a moment with no connection to anything the user did.
    default_time_zone: str = DEFAULT_TIME_ZONE

    # Message bus (NTF-201, NTF-202). Commerce appends order lifecycle events to a Redis stream
    # (COM-109); this service consumes that stream as a named consumer group, so competing
    # replicas each get a disjoint slice and no event is delivered twice. The stream name must
    # match COMMERCE_EVENT_STREAM. Leave NOTIFICATION_EVENT_BUS_URL blank and the bus falls back
    # to ``redis_url`` -- one Redis backs both in every environment we run today, and splitting
    # them stays a config change rather than a code change.
    event_bus_url: str = ""
    order_event_stream: str = "commerce.order-events"
    consumer_group: str = "notification"
    consumer_name: str = "notification-1"
    event_batch_size: int = 32
    event_block_ms: int = 5_000
    # How long a delivered-but-unacked event must sit idle before another consumer takes it
    # over. This is the mechanism that recovers events stranded by a pod that died mid-batch,
    # so it has to be comfortably longer than a slow-but-healthy handler takes -- reclaiming
    # an event still being processed produces the duplicate NTF-103 then has to suppress.
    event_reclaim_idle_ms: int = 60_000
    # Retry budget before an event is parked on the dead-letter queue (NTF-204).
    event_max_delivery_attempts: int = 5
    # How long an order's announced progress is remembered (NTF-202). This is what lets a
    # stale status -- ``in_transit`` arriving after ``delivered`` -- be recognised as stale
    # rather than announced, so it must outlive the longest plausible order by a wide margin;
    # a week covers a grocery delivery scheduled days out with room to spare. It is not a
    # substitute for the dedupe window: that suppresses a *replay of one event*, this
    # suppresses a *different, older event*, and the two windows expire independently.
    order_progress_ttl_seconds: int = 604_800

    # Push providers (NTF-301). Android goes through FCM, iOS through APNs; the concrete
    # clients arrive with that story, so this slice owns only the configuration surface and the
    # readiness signal derived from it. Credentials are injected per environment from the
    # vault. Push is considered configured once *either* provider has credentials, so a
    # single-platform environment is still ready.
    push_enabled: bool = True
    fcm_project_id: str = ""
    fcm_credentials_json: SecretStr = SecretStr("")
    apns_team_id: str = ""
    apns_key_id: str = ""
    apns_bundle_id: str = "mx.nutriplan.app"
    apns_private_key: SecretStr = SecretStr("")
    apns_use_sandbox: bool = True

    # Access-token verification (NTF-105, NTF-702). The in-app feed API is a resource server:
    # it verifies RS256 tokens minted by Identity against its published JWKS, so iss/aud must
    # match what Identity issues.
    identity_jwks_url: str = "http://identity:8081/.well-known/jwks.json"
    jwt_issuer: str = "nutriplan-identity"
    jwt_audience: str = "nutriplan"

    http_timeout_seconds: float = 5.0

    @property
    def is_production(self) -> bool:
        """True in production-like environments, where a missing dependency is fatal."""
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def redis_configured(self) -> bool:
        """True once a Redis URL is present, so notification state can be shared."""
        return bool(self.redis_url.strip())

    @property
    def effective_event_bus_url(self) -> str:
        """The bus URL actually used: the explicit one, else the datastore's Redis."""
        return self.event_bus_url.strip() or self.redis_url.strip()

    @property
    def event_bus_configured(self) -> bool:
        """True once the service has somewhere to consume domain events from."""
        return bool(self.effective_event_bus_url)

    @property
    def fcm_configured(self) -> bool:
        """True once FCM can be called, so Android devices are reachable."""
        return bool(self.fcm_project_id.strip() and self.fcm_credentials_json.get_secret_value())

    @property
    def apns_configured(self) -> bool:
        """True once APNs can be called, so iOS devices are reachable."""
        return bool(
            self.apns_team_id.strip()
            and self.apns_key_id.strip()
            and self.apns_private_key.get_secret_value()
        )

    @property
    def push_configured(self) -> bool:
        """True when at least one push provider is usable; disabling push satisfies this."""
        if not self.push_enabled:
            return True
        return self.fcm_configured or self.apns_configured


settings = Settings()
