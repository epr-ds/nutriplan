"""Device-token registration and revocation (NTF-302).

Two operations, both owner-scoped by the token subject:

* ``POST /notifications/devices`` registers the token the app currently holds. It is
  idempotent by design -- the token is the identity, so the same call on every launch
  refreshes one record instead of adding another. A token that arrives under a different
  account is moved to that account, because a phone that changed hands must not keep
  receiving the previous owner's notifications.
* ``DELETE /notifications/devices/{deviceId}`` removes one of the caller's registrations.
  Revoking an id that is unknown, already revoked, or owned by somebody else is the same
  ``404``, so the endpoint cannot be used to enumerate other users' devices.

Dead tokens reported by FCM/APNs are pruned through the service, not through this router:
that feedback arrives on the delivery path, where there is no user request to scope it to.

Route order: this router is included before the feed router, alongside preferences. The
literal ``/notifications/devices`` segment is not currently shadowed by a parameterised feed
route, but keeping specific literals registered first is the rule that made preferences
reachable and the reason it stayed that way.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUserId, DeviceServiceDep
from app.api.schemas import RegisterDeviceRequest, RegisteredDeviceResponse

router = APIRouter(tags=["Notifications"])


@router.post(
    "/notifications/devices",
    response_model=RegisteredDeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or refresh a push device token",
)
def register_device(
    user_id: CurrentUserId,
    request: RegisterDeviceRequest,
    devices: DeviceServiceDep,
) -> RegisteredDeviceResponse:
    """Register the caller's push token, refreshing it if it is already known.

    A ``201`` is returned for a new registration and for a refresh alike: the client's action
    -- "make this token mine" -- is the same either way, and a client that had to branch on
    ``200`` versus ``201`` would be encoding a distinction it does not act on. The returned id
    is stable across refreshes, so it can be stored and used to revoke later.
    """
    return RegisteredDeviceResponse.from_domain(
        devices.register(user_id, request.platform, request.token)
    )


@router.delete(
    "/notifications/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a registered push device token",
)
def revoke_device(
    device_id: uuid.UUID,
    user_id: CurrentUserId,
    devices: DeviceServiceDep,
) -> Response:
    """Remove one of the caller's device registrations.

    ``204`` carries no body because nothing about the client's state remains to report: the
    registration is gone. Revoking a device that is not registered to the caller is a ``404``
    rather than a silent success, so a bug that loses the id is visible instead of leaving a
    phone quietly receiving pushes.
    """
    devices.revoke(user_id, device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
