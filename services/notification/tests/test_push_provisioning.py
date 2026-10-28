"""NTF-705: push credential provisioning (FCM service account + APNs key/cert) per environment."""

from __future__ import annotations

from pydantic import SecretStr

from app.adapters.apns_adapter import APNsConfig
from app.adapters.factory import provision_apns, provision_fcm
from app.adapters.fcm_adapter import FCMConfig
from app.core.config import Settings


def test_provision_fcm_resolves_the_vault_service_account() -> None:
    """NTF-705: the vault-injected FCM service account becomes a usable adapter config."""
    settings = Settings(
        environment="staging",
        fcm_project_id="nutriplan",
        fcm_credentials_json=SecretStr(
            '{"type": "service_account", "client_email": "svc@n.iam.gserviceaccount.com"}'
        ),
    )

    config = provision_fcm(settings)

    assert isinstance(config, FCMConfig)
    assert config.project_id == "nutriplan"
    assert config.credentials_json["client_email"] == "svc@n.iam.gserviceaccount.com"


def test_provision_fcm_is_unconfigured_without_credentials() -> None:
    """NTF-705: an environment with no vault credentials has no FCM provider to provision."""
    assert provision_fcm(Settings(environment="staging")) is None


def test_provision_apns_resolves_sandbox_vs_prod_per_environment() -> None:
    """NTF-705: the APNs key/cert is resolved per environment -- sandbox vs the live endpoint."""

    def apns_settings(environment: str) -> Settings:
        return Settings(
            environment=environment,
            apns_team_id="TEAM123",
            apns_key_id="KEY456",
            apns_private_key=SecretStr("fake-apns-pem-key"),
            apns_bundle_id="mx.nutriplan.app",
        )

    staging = provision_apns(apns_settings("staging"))
    assert isinstance(staging, APNsConfig)
    assert staging.use_sandbox is True
    assert staging.team_id == "TEAM123"
    assert staging.key_id == "KEY456"
    assert staging.auth_key == b"fake-apns-pem-key"

    prod = provision_apns(apns_settings("production"))
    assert isinstance(prod, APNsConfig)
    assert prod.use_sandbox is False
