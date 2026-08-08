from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode
from uuid import UUID, uuid4

from legal_workbench.application.idempotency import request_hash, require_matching_replay
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import (
    AuditEvent,
    FeishuOAuthAttempt,
    FeishuUserAuthorization,
    IdempotencyRecord,
)
from legal_workbench.domain.enums import (
    FeishuTokenRotationPhase,
    FeishuUserAuthorizationStatus,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.infrastructure.secrets import LocalSecretProvider

DEFAULT_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"


def build_pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _oauth_state_reference(verifier_reference: str) -> str:
    return f"{verifier_reference}_state"


@dataclass(frozen=True, slots=True)
class FeishuOAuthTokens:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OAuthIdentity:
    open_id: str
    union_id: str | None
    tenant_key: str
    display_name: str | None


@dataclass(frozen=True, slots=True)
class OAuthStartResult:
    authorization_url: str
    state: str
    verifier_reference: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class _RotationClaim:
    authorization_id: UUID
    owner: str
    generation: int
    fence: int
    bundle_ref: str
    refresh_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class _RotationPreparation:
    access_token: str | None = None
    claim: _RotationClaim | None = None
    wait_for_owner: bool = False


class FeishuOAuthClientProtocol(Protocol):
    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> FeishuOAuthTokens: ...
    async def get_identity(self, *, access_token: str) -> OAuthIdentity: ...
    async def refresh(self, *, refresh_token: str) -> FeishuOAuthTokens: ...


class FeishuOAuthService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        oauth_client: FeishuOAuthClientProtocol,
        secret_provider: LocalSecretProvider,
        app_id: str,
        authorize_url: str = DEFAULT_AUTHORIZE_URL,
        attempt_ttl: timedelta = timedelta(minutes=10),
        required_scopes: tuple[str, ...] = (),
    ) -> None:
        self._uow_factory = uow_factory
        self._oauth_client = oauth_client
        self._secret_provider = secret_provider
        self._app_id = app_id.strip()
        self._authorize_url = authorize_url
        self._attempt_ttl = attempt_ttl
        self._required_scopes = frozenset(required_scopes)

    def _authorization_url(
        self,
        *,
        redirect_uri: str,
        scopes: tuple[str, ...],
        state: str,
        verifier: str,
    ) -> str:
        query = urlencode(
            {
                "app_id": self._app_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state,
                "code_challenge": build_pkce_challenge(verifier),
                "code_challenge_method": "S256",
            }
        )
        return f"{self._authorize_url}?{query}"

    async def start_authorization(
        self,
        *,
        redirect_uri: str,
        requested_by: str,
        scopes: tuple[str, ...],
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> OAuthStartResult:
        if not self._app_id or not redirect_uri.strip() or not requested_by.strip():
            raise DomainValidationError("OAuth application, redirect URI and actor are required.")
        normalized_scopes = tuple(dict.fromkeys(scope.strip() for scope in scopes if scope.strip()))
        if "offline_access" not in normalized_scopes:
            raise DomainValidationError("Feishu user authorization requires offline_access.")
        attempt_id = uuid4()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        verifier_reference = f"feishu_pkce_{attempt_id.hex}"
        state_reference = _oauth_state_reference(verifier_reference)
        expires_at = datetime.now(UTC) + self._attempt_ttl
        self._secret_provider.write(verifier_reference, verifier)
        self._secret_provider.write(state_reference, state)
        attempt = FeishuOAuthAttempt(
            id=attempt_id,
            state_hash=hashlib.sha256(state.encode("utf-8")).hexdigest(),
            code_verifier_ref=verifier_reference,
            redirect_uri=redirect_uri.strip(),
            scopes=normalized_scopes,
            requested_by=requested_by.strip(),
            expires_at=expires_at,
        )
        authorization_url = self._authorization_url(
            redirect_uri=attempt.redirect_uri,
            scopes=normalized_scopes,
            state=state,
            verifier=verifier,
        )
        try:
            async with self._uow_factory() as uow:
                digest = request_hash(
                    {
                        "redirectUri": attempt.redirect_uri,
                        "requestedBy": requested_by,
                        "scopes": normalized_scopes,
                    }
                )
                operation = "start_feishu_user_authorization"
                if idempotency_key is not None:
                    await uow.lock_idempotency(
                        operation=operation, key=idempotency_key
                    )
                    replay = require_matching_replay(
                        await uow.idempotency.get(
                            operation=operation, key=idempotency_key
                        ),
                        expected_hash=digest,
                        idempotency_key=idempotency_key,
                    )
                    if replay is not None:
                        self._secret_provider.delete(verifier_reference)
                        self._secret_provider.delete(state_reference)
                        replay_verifier_reference = str(
                            replay.response_payload["verifierReference"]
                        )
                        replay_state_reference = str(
                            replay.response_payload["stateReference"]
                        )
                        replay_state = self._secret_provider.read(
                            replay_state_reference
                        )
                        replay_verifier = self._secret_provider.read(
                            replay_verifier_reference
                        )
                        raw_replay_scopes = replay.response_payload["scopes"]
                        if not isinstance(raw_replay_scopes, list):
                            raise DomainValidationError(
                                "Stored OAuth scope replay is invalid."
                            )
                        replay_scopes = tuple(str(value) for value in raw_replay_scopes)
                        replay_redirect_uri = str(
                            replay.response_payload["redirectUri"]
                        )
                        return OAuthStartResult(
                            authorization_url=self._authorization_url(
                                redirect_uri=replay_redirect_uri,
                                scopes=replay_scopes,
                                state=replay_state,
                                verifier=replay_verifier,
                            ),
                            state=replay_state,
                            verifier_reference=replay_verifier_reference,
                            expires_at=datetime.fromisoformat(
                                str(replay.response_payload["expiresAt"])
                            ),
                        )
                await uow.feishu_user_authorizations.add_oauth_attempt(attempt)
                if correlation_id is not None:
                    await uow.audit_events.add(
                        AuditEvent(
                            id=uuid4(),
                            aggregate_type="feishu_oauth_attempt",
                            aggregate_id=attempt.id,
                            event_type="feishu_user_authorization_started",
                            actor_id=requested_by,
                            actor_source="user",
                            payload={"scopes": list(normalized_scopes)},
                            correlation_id=correlation_id,
                        )
                    )
                if idempotency_key is not None:
                    await uow.idempotency.add(
                        IdempotencyRecord(
                            id=uuid4(),
                            operation=operation,
                            idempotency_key=idempotency_key,
                            request_hash=digest,
                            response_payload={
                                "verifierReference": verifier_reference,
                                "stateReference": state_reference,
                                "redirectUri": attempt.redirect_uri,
                                "scopes": list(normalized_scopes),
                                "expiresAt": expires_at.isoformat(),
                            },
                        )
                    )
                await uow.commit()
        except Exception:
            self._secret_provider.delete(verifier_reference)
            self._secret_provider.delete(state_reference)
            raise
        return OAuthStartResult(
            authorization_url=authorization_url,
            state=state,
            verifier_reference=verifier_reference,
            expires_at=expires_at,
        )

    async def complete_authorization(
        self,
        *,
        state: str,
        code: str,
    ) -> FeishuUserAuthorization:
        state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
        access_ref: str | None = None
        refresh_ref: str | None = None
        verifier_ref: str | None = None
        try:
            async with self._uow_factory() as uow:
                attempt = await uow.feishu_user_authorizations.get_oauth_attempt_for_update(
                    state_hash
                )
                if attempt is None:
                    raise DomainValidationError("OAuth state is invalid.")
                attempt.consume()
                verifier_ref = attempt.code_verifier_ref
                await uow.feishu_user_authorizations.save_oauth_attempt(attempt)
                await uow.commit()

            verifier = self._secret_provider.read(verifier_ref)
            tokens = await self._oauth_client.exchange_code(
                code=code,
                code_verifier=verifier,
                redirect_uri=attempt.redirect_uri,
            )
            identity = await self._oauth_client.get_identity(
                access_token=tokens.access_token
            )
            authorization_id = uuid4()
            access_ref = f"feishu_uat_{authorization_id.hex}_v1"
            refresh_ref = f"feishu_urt_{authorization_id.hex}_v1"
            self._secret_provider.write(access_ref, tokens.access_token)
            self._secret_provider.write(refresh_ref, tokens.refresh_token)
            authorization = FeishuUserAuthorization(
                id=authorization_id,
                open_id=identity.open_id,
                union_id=identity.union_id,
                tenant_key=identity.tenant_key,
                display_name=identity.display_name,
                scopes=tokens.scopes,
                access_token_ref=access_ref,
                refresh_token_ref=refresh_ref,
                access_expires_at=tokens.access_expires_at,
                refresh_expires_at=tokens.refresh_expires_at,
                token_version=1,
                status=(
                    FeishuUserAuthorizationStatus.PERMISSION_MISSING
                    if self._required_scopes.difference(tokens.scopes)
                    else FeishuUserAuthorizationStatus.CONNECTED
                ),
                last_error_code=(
                    "permission_missing"
                    if self._required_scopes.difference(tokens.scopes)
                    else None
                ),
            )
            async with self._uow_factory() as uow:
                await uow.feishu_user_authorizations.add_authorization(authorization)
                await uow.audit_events.add(
                    AuditEvent(
                        id=uuid4(),
                        aggregate_type="feishu_user_authorization",
                        aggregate_id=authorization.id,
                        event_type="feishu_user_authorization_completed",
                        actor_id=attempt.requested_by,
                        actor_source="user",
                        payload={
                            "openId": identity.open_id,
                            "tenantKey": identity.tenant_key,
                            "scopes": list(tokens.scopes),
                        },
                        correlation_id=f"feishu-oauth:{attempt.id}",
                    )
                )
                await uow.commit()
        except Exception:
            if access_ref is not None:
                self._secret_provider.delete(access_ref)
            if refresh_ref is not None:
                self._secret_provider.delete(refresh_ref)
            raise
        finally:
            if verifier_ref is not None:
                self._secret_provider.delete(verifier_ref)
                self._secret_provider.delete(_oauth_state_reference(verifier_ref))
        return authorization

    async def list_authorizations(self) -> tuple[FeishuUserAuthorization, ...]:
        async with self._uow_factory() as uow:
            values = await uow.feishu_user_authorizations.list_authorizations()
        return tuple(values)

    async def disconnect(
        self,
        authorization_id: UUID,
        *,
        actor_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> FeishuUserAuthorization:
        access_ref: str | None = None
        refresh_ref: str | None = None
        async with self._uow_factory() as uow:
            operation = "disconnect_feishu_user_authorization"
            digest = request_hash({"authorizationId": authorization_id})
            if idempotency_key is not None:
                await uow.lock_idempotency(operation=operation, key=idempotency_key)
                replay = require_matching_replay(
                    await uow.idempotency.get(
                        operation=operation, key=idempotency_key
                    ),
                    expected_hash=digest,
                    idempotency_key=idempotency_key,
                )
                if replay is not None:
                    stored = await uow.feishu_user_authorizations.get_authorization(
                        authorization_id
                    )
                    if stored is None:
                        raise DomainValidationError(
                            "Feishu user authorization was not found."
                        )
                    return stored
            authorization = (
                await uow.feishu_user_authorizations.get_authorization_for_update(
                    authorization_id
                )
            )
            if authorization is None:
                raise DomainValidationError("Feishu user authorization was not found.")
            access_ref = authorization.access_token_ref
            refresh_ref = authorization.refresh_token_ref
            authorization.status = FeishuUserAuthorizationStatus.REVOKED
            authorization.last_error_code = None
            authorization.updated_at = datetime.now(UTC)
            await uow.feishu_user_authorizations.save_authorization(authorization)
            if actor_id is not None and correlation_id is not None:
                await uow.audit_events.add(
                    AuditEvent(
                        id=uuid4(),
                        aggregate_type="feishu_user_authorization",
                        aggregate_id=authorization.id,
                        event_type="feishu_user_authorization_revoked",
                        actor_id=actor_id,
                        actor_source="user",
                        payload={"status": authorization.status.value},
                        correlation_id=correlation_id,
                    )
                )
            if idempotency_key is not None:
                await uow.idempotency.add(
                    IdempotencyRecord(
                        id=uuid4(),
                        operation=operation,
                        idempotency_key=idempotency_key,
                        request_hash=digest,
                        response_payload={"authorizationId": str(authorization.id)},
                    )
                )
            await uow.commit()
        self._secret_provider.delete(access_ref)
        self._secret_provider.delete(refresh_ref)
        return authorization


class FeishuUserTokenProvider:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        oauth_client: FeishuOAuthClientProtocol,
        secret_provider: LocalSecretProvider,
        refresh_skew: timedelta = timedelta(minutes=5),
        required_scopes: tuple[str, ...] = (),
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._oauth_client = oauth_client
        self._secret_provider = secret_provider
        self._refresh_skew = refresh_skew
        self._required_scopes = frozenset(required_scopes)
        self._fault_injector = fault_injector

    def _inject_fault(self, stage: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage)

    async def get_access_token(
        self, authorization_id: UUID, *, force_refresh: bool = False
    ) -> str:
        waited_for_rotation = False
        for _attempt in range(200):
            preparation = await self._prepare_rotation(
                authorization_id,
                force_refresh=force_refresh and not waited_for_rotation,
            )
            if preparation.access_token is not None:
                return preparation.access_token
            if preparation.wait_for_owner:
                waited_for_rotation = True
                await asyncio.sleep(0.02)
                continue
            claim = preparation.claim
            if claim is None:
                raise RuntimeError("Token rotation preparation is invalid.")
            self._inject_fault("before_request_started")
            await self._mark_request_started(claim)
            try:
                self._inject_fault("after_request_started")
                rotated = await self._oauth_client.refresh(
                    refresh_token=claim.refresh_token
                )
                self._inject_fault("after_http_success_before_bundle")
                self._secret_provider.write_token_generation(
                    claim.bundle_ref,
                    access_token=rotated.access_token,
                    refresh_token=rotated.refresh_token,
                    access_expires_at=rotated.access_expires_at,
                    refresh_expires_at=rotated.refresh_expires_at,
                    scopes=rotated.scopes,
                )
                self._inject_fault("after_bundle_fsync")
                await self._mark_result_durable(claim)
                self._inject_fault("before_activation_commit")
                return await self._activate_pending_generation(
                    authorization_id,
                    claim=claim,
                    inject_faults=True,
                )
            except Exception as exc:
                if not self._secret_provider.exists(claim.bundle_ref):
                    await self._record_rotation_failure(claim, exc)
                raise
        raise DomainValidationError("Feishu user token rotation is still in progress.")

    async def _prepare_rotation(
        self, authorization_id: UUID, *, force_refresh: bool
    ) -> _RotationPreparation:
        async with self._uow_factory() as uow:
            authorization = (
                await uow.feishu_user_authorizations.get_authorization_for_update(
                    authorization_id
                )
            )
            if authorization is None:
                raise DomainValidationError("Feishu user authorization was not found.")
            now = datetime.now(UTC)
            bundle_ref = authorization.pending_token_bundle_ref
            if bundle_ref and self._secret_provider.exists(bundle_ref):
                return _RotationPreparation(
                    access_token=await self._activate_locked_generation(
                        uow=uow,
                        authorization=authorization,
                        now=now,
                        claim=None,
                        inject_faults=False,
                    )
                )
            if authorization.pending_token_version is not None:
                if (
                    authorization.rotation_expires_at is not None
                    and authorization.rotation_expires_at > now
                ):
                    return _RotationPreparation(wait_for_owner=True)
                if (
                    authorization.rotation_phase
                    == FeishuTokenRotationPhase.CLAIMED
                    and authorization.rotation_request_started_at is None
                ):
                    authorization.clear_pending_rotation()
                    authorization.rotation_phase = FeishuTokenRotationPhase.IDLE
                    authorization.status = FeishuUserAuthorizationStatus.CONNECTED
                    authorization.last_error_code = None
                    authorization.updated_at = now
                    await uow.feishu_user_authorizations.save_authorization(authorization)
                    await uow.commit()
                else:
                    authorization.status = FeishuUserAuthorizationStatus.REAUTH_REQUIRED
                    authorization.last_error_code = "rotation_result_missing"
                    authorization.rotation_reauth_reason = "refresh_outcome_uncertain"
                    if authorization.rotation_phase == FeishuTokenRotationPhase.IDLE:
                        authorization.rotation_phase = (
                            FeishuTokenRotationPhase.REQUEST_STARTED
                        )
                    authorization.updated_at = now
                    authorization.clear_pending_rotation()
                    await uow.feishu_user_authorizations.save_authorization(authorization)
                    await uow.commit()
                    raise DomainValidationError(
                        "Feishu token rotation was interrupted; authorization must be renewed."
                    )
            self._cleanup_known_orphans(authorization)
            if (
                authorization.status
                == FeishuUserAuthorizationStatus.PERMISSION_MISSING
                and not self._required_scopes.difference(authorization.scopes)
            ):
                authorization.status = FeishuUserAuthorizationStatus.CONNECTED
                authorization.last_error_code = None
                authorization.updated_at = now
                await uow.feishu_user_authorizations.save_authorization(authorization)
                await uow.commit()
            if authorization.status not in {
                FeishuUserAuthorizationStatus.CONNECTED,
                FeishuUserAuthorizationStatus.DEGRADED,
            }:
                raise DomainValidationError("Feishu user authorization requires attention.")
            if (
                not force_refresh
                and authorization.access_expires_at > now + self._refresh_skew
            ):
                return _RotationPreparation(
                    access_token=self._secret_provider.read(
                        authorization.access_token_ref
                    )
                )
            if authorization.refresh_expires_at <= now:
                authorization.status = FeishuUserAuthorizationStatus.EXPIRED
                authorization.last_error_code = "refresh_token_expired"
                authorization.updated_at = now
                await uow.feishu_user_authorizations.save_authorization(authorization)
                await uow.commit()
                raise DomainValidationError("Feishu user authorization must be renewed.")
            owner = uuid4().hex
            generation = authorization.token_version + 1
            bundle_ref = f"feishu_rotation_{authorization.id.hex}_v{generation}"
            authorization.pending_token_version = generation
            authorization.pending_token_bundle_ref = bundle_ref
            authorization.rotation_owner = owner
            authorization.rotation_expires_at = now + timedelta(minutes=2)
            authorization.rotation_fence += 1
            authorization.rotation_phase = FeishuTokenRotationPhase.CLAIMED
            authorization.rotation_request_started_at = None
            authorization.rotation_result_written_at = None
            authorization.rotation_reauth_reason = None
            authorization.status = FeishuUserAuthorizationStatus.REFRESHING
            authorization.updated_at = now
            refresh_token = self._secret_provider.read(
                authorization.refresh_token_ref
            )
            await uow.feishu_user_authorizations.save_authorization(authorization)
            await uow.commit()
            return _RotationPreparation(
                claim=_RotationClaim(
                    authorization_id=authorization.id,
                    owner=owner,
                    generation=generation,
                    fence=authorization.rotation_fence,
                    bundle_ref=bundle_ref,
                    refresh_token=refresh_token,
                )
            )

    async def _mark_request_started(self, claim: _RotationClaim) -> None:
        async with self._uow_factory() as uow:
            authorization = (
                await uow.feishu_user_authorizations.get_authorization_for_update(
                    claim.authorization_id
                )
            )
            if authorization is None:
                raise DomainValidationError("Feishu user authorization was not found.")
            self._require_current_claim(authorization, claim)
            if authorization.rotation_phase != FeishuTokenRotationPhase.CLAIMED:
                raise DomainValidationError("Feishu token rotation phase is invalid.")
            now = datetime.now(UTC)
            authorization.rotation_phase = FeishuTokenRotationPhase.REQUEST_STARTED
            authorization.rotation_request_started_at = now
            authorization.updated_at = now
            await uow.feishu_user_authorizations.save_authorization(authorization)
            await uow.commit()

    async def _mark_result_durable(self, claim: _RotationClaim) -> None:
        async with self._uow_factory() as uow:
            authorization = (
                await uow.feishu_user_authorizations.get_authorization_for_update(
                    claim.authorization_id
                )
            )
            if authorization is None:
                raise DomainValidationError("Feishu user authorization was not found.")
            self._require_current_claim(authorization, claim)
            if (
                authorization.rotation_phase
                != FeishuTokenRotationPhase.REQUEST_STARTED
                or not self._secret_provider.exists(claim.bundle_ref)
            ):
                raise DomainValidationError("Feishu token rotation result is not durable.")
            now = datetime.now(UTC)
            authorization.rotation_phase = FeishuTokenRotationPhase.RESULT_DURABLE
            authorization.rotation_result_written_at = now
            authorization.updated_at = now
            await uow.feishu_user_authorizations.save_authorization(authorization)
            await uow.commit()

    async def _activate_pending_generation(
        self,
        authorization_id: UUID,
        *,
        claim: _RotationClaim | None,
        inject_faults: bool,
    ) -> str:
        async with self._uow_factory() as uow:
            authorization = (
                await uow.feishu_user_authorizations.get_authorization_for_update(
                    authorization_id
                )
            )
            if authorization is None:
                raise DomainValidationError("Feishu user authorization was not found.")
            if authorization.pending_token_bundle_ref is None:
                return self._secret_provider.read(authorization.access_token_ref)
            return await self._activate_locked_generation(
                uow=uow,
                authorization=authorization,
                now=datetime.now(UTC),
                claim=claim,
                inject_faults=inject_faults,
            )

    async def _activate_locked_generation(
        self,
        *,
        uow: object,
        authorization: FeishuUserAuthorization,
        now: datetime,
        claim: _RotationClaim | None,
        inject_faults: bool,
    ) -> str:
        generation = authorization.pending_token_version
        bundle_ref = authorization.pending_token_bundle_ref
        if generation is None or bundle_ref is None:
            raise DomainValidationError("Pending token generation is incomplete.")
        if generation != authorization.token_version + 1:
            raise DomainValidationError("Pending token generation is out of sequence.")
        if claim is not None:
            self._require_current_claim(authorization, claim)
        bundle = self._secret_provider.read_token_generation(bundle_ref)
        old_access_ref = authorization.access_token_ref
        old_refresh_ref = authorization.refresh_token_ref
        new_access_ref = f"feishu_uat_{authorization.id.hex}_v{generation}"
        new_refresh_ref = f"feishu_urt_{authorization.id.hex}_v{generation}"
        self._secret_provider.write(new_access_ref, bundle.access_token)
        self._secret_provider.write(new_refresh_ref, bundle.refresh_token)
        authorization.rotate(
            access_token_ref=new_access_ref,
            refresh_token_ref=new_refresh_ref,
            access_expires_at=bundle.access_expires_at,
            refresh_expires_at=bundle.refresh_expires_at,
            scopes=bundle.scopes,
            now=now,
        )
        authorization.clear_pending_rotation()
        authorization.rotation_phase = FeishuTokenRotationPhase.ACTIVATED
        if self._required_scopes.difference(bundle.scopes):
            authorization.status = FeishuUserAuthorizationStatus.PERMISSION_MISSING
            authorization.last_error_code = "permission_missing"
        await uow.feishu_user_authorizations.save_authorization(authorization)  # type: ignore[attr-defined]
        await uow.audit_events.add(  # type: ignore[attr-defined]
            AuditEvent(
                id=uuid4(),
                aggregate_type="feishu_user_authorization",
                aggregate_id=authorization.id,
                event_type="feishu_user_token_rotated",
                actor_id="feishu-user-token-provider",
                actor_source="system",
                payload={"tokenVersion": authorization.token_version},
                correlation_id=f"feishu-user-token-refresh:{authorization.id}",
            )
        )
        await uow.commit()  # type: ignore[attr-defined]
        if inject_faults:
            self._inject_fault("after_activation_commit")
            self._inject_fault("during_orphan_cleanup")
        self._secret_provider.delete(bundle_ref)
        if old_access_ref != new_access_ref:
            self._secret_provider.delete(old_access_ref)
        if old_refresh_ref != new_refresh_ref:
            self._secret_provider.delete(old_refresh_ref)
        self._cleanup_known_orphans(authorization)
        return bundle.access_token

    @staticmethod
    def _require_current_claim(
        authorization: FeishuUserAuthorization,
        claim: _RotationClaim,
    ) -> None:
        if (
            authorization.pending_token_version != claim.generation
            or authorization.pending_token_bundle_ref != claim.bundle_ref
            or authorization.rotation_owner != claim.owner
            or authorization.rotation_fence != claim.fence
        ):
            raise DomainValidationError("Feishu token rotation claim was fenced.")

    def _cleanup_known_orphans(self, authorization: FeishuUserAuthorization) -> None:
        active_refs = {
            authorization.access_token_ref,
            authorization.refresh_token_ref,
            authorization.pending_token_bundle_ref,
        }
        for generation in range(1, authorization.token_version + 1):
            for reference in (
                f"feishu_uat_{authorization.id.hex}_v{generation}",
                f"feishu_urt_{authorization.id.hex}_v{generation}",
                f"feishu_rotation_{authorization.id.hex}_v{generation}",
            ):
                if reference not in active_refs:
                    self._secret_provider.delete(reference)

    async def _record_rotation_failure(
        self, claim: _RotationClaim, exc: Exception
    ) -> None:
        async with self._uow_factory() as uow:
            authorization = (
                await uow.feishu_user_authorizations.get_authorization_for_update(
                    claim.authorization_id
                )
            )
            if authorization is None:
                return
            if (
                authorization.pending_token_version != claim.generation
                or authorization.rotation_owner != claim.owner
                or authorization.rotation_fence != claim.fence
            ):
                return
            http_status = getattr(exc, "http_status", None)
            error_code = str(getattr(exc, "code", "refresh_failed"))
            if http_status in {400, 401}:
                authorization.status = FeishuUserAuthorizationStatus.REAUTH_REQUIRED
                prefix = "refresh_rejected"
                authorization.rotation_reauth_reason = "refresh_rejected"
            else:
                authorization.status = FeishuUserAuthorizationStatus.REAUTH_REQUIRED
                prefix = "refresh_outcome_uncertain"
                authorization.rotation_reauth_reason = "refresh_outcome_uncertain"
            authorization.last_error_code = f"{prefix}:{error_code}"[:100]
            authorization.updated_at = datetime.now(UTC)
            authorization.clear_pending_rotation()
            await uow.feishu_user_authorizations.save_authorization(authorization)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="feishu_user_authorization",
                    aggregate_id=authorization.id,
                    event_type="feishu_user_token_refresh_failed",
                    actor_id="feishu-user-token-provider",
                    actor_source="system",
                    payload={
                        "status": authorization.status.value,
                        "errorCode": authorization.last_error_code,
                    },
                    correlation_id=f"feishu-user-token-refresh:{authorization.id}",
                )
            )
            await uow.commit()
