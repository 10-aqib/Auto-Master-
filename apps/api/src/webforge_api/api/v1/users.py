"""/api/v1/users — account administration (OWNER, ADMIN)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from webforge_api.api.deps import MetaDep, OwnerOnly, OwnerOrAdmin, UserServiceDep
from webforge_api.api.v1.schemas import CountResponse, UserCreateRequest, UserOut, UserUpdateRequest
from webforge_api.services.users import UserChanges

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(_principal: OwnerOrAdmin, users: UserServiceDep) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in users.list_users()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateRequest, principal: OwnerOrAdmin, users: UserServiceDep, meta: MetaDep
) -> UserOut:
    user = users.create_user(
        principal,
        email=body.email,
        display_name=body.display_name,
        role=body.role,
        initial_password=body.initial_password,
        meta=meta,
    )
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    principal: OwnerOrAdmin,
    users: UserServiceDep,
    meta: MetaDep,
) -> UserOut:
    changes = UserChanges(display_name=body.display_name, role=body.role, is_active=body.is_active)
    return UserOut.model_validate(users.update_user(principal, user_id, changes, meta))


@router.post("/{user_id}/revoke-sessions", response_model=CountResponse)
def revoke_sessions(
    user_id: uuid.UUID, principal: OwnerOrAdmin, users: UserServiceDep, meta: MetaDep
) -> CountResponse:
    return CountResponse(count=users.revoke_sessions(principal, user_id, meta))


@router.post("/{user_id}/reset-mfa", status_code=status.HTTP_204_NO_CONTENT)
def reset_mfa(
    user_id: uuid.UUID, principal: OwnerOnly, users: UserServiceDep, meta: MetaDep
) -> Response:
    users.reset_mfa(principal, user_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
