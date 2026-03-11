# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Callable, List, Literal, Optional, TypeVar

from app.api.deps import verify_novel_access
from app.config import get_settings
from app.core.bootstrap import (
    resolve_bootstrap_mode,
)
from app.core.auth import (
    get_current_user_or_default,
    check_generation_quota,
)
from app.core.llm_request import get_llm_config
from app.core.world_application import (
    batch_confirm_entities as confirm_entity_drafts,
    batch_confirm_relationships as confirm_relationship_drafts,
    batch_confirm_systems as confirm_system_drafts,
    batch_reject_entities as reject_entity_drafts,
    batch_reject_relationships as reject_relationship_drafts,
    batch_reject_systems as reject_system_drafts,
    create_attribute as create_attribute_use_case,
    create_entity as create_entity_use_case,
    create_relationship as create_relationship_use_case,
    create_system as create_system_use_case,
    delete_attribute as delete_attribute_use_case,
    delete_entity as delete_entity_use_case,
    delete_relationship as delete_relationship_use_case,
    delete_system as delete_system_use_case,
    reorder_attributes as reorder_attribute_values,
    update_attribute as update_attribute_use_case,
    update_entity as update_entity_use_case,
    update_relationship as update_relationship_use_case,
    update_system as update_system_use_case,
)
from app.core.world_bootstrap_application import (
    get_bootstrap_status as get_bootstrap_status_use_case,
    is_bootstrap_initialized,
    trigger_bootstrap as trigger_bootstrap_use_case,
)
from app.core.world_crud import (
    WorldCrudDetailError,
    WorldCrudError,
    load_entity,
    load_novel,
    load_relationship,
    load_system,
)
from app.core.world_generation_application import generate_world_from_text as generate_world_from_text_use_case
from app.core.world_use_case_errors import WorldUseCaseDetailError, WorldUseCaseError
from app.core.worldpack_import import (
    UnsupportedWorldpackSchemaVersionError,
    WorldpackImportConflictError,
    WorldpackImportError,
    WorldpackImportResult,
    WorldpackNovelNotFoundError,
    import_worldpack_payload,
)
from app.database import get_db
from app.models import (
    BootstrapJob,
    Novel,
    User,
    WorldEntity,
    WorldRelationship,
    WorldSystem,
)
from app.schemas import (
    AttributeReorderRequest,
    BatchConfirmRequest,
    BatchConfirmResponse,
    BatchRejectRequest,
    BatchRejectResponse,
    BootstrapJobResponse,
    BootstrapMode,
    BootstrapProgress,
    BootstrapResult,
    BootstrapTriggerRequest,
    WorldAttributeCreate,
    WorldAttributeUpdate,
    WorldEntityAttributeResponse,
    WorldEntityCreate,
    WorldEntityDetailResponse,
    WorldEntityResponse,
    WorldEntityUpdate,
    WorldRelationshipCreate,
    WorldRelationshipResponse,
    WorldRelationshipUpdate,
    WorldSystemCreate,
    WorldSystemResponse,
    WorldSystemUpdate,
    WorldpackImportCounts,
    WorldpackImportResponse,
    WorldpackImportWarning,
    WorldpackV1Payload,
    WorldGenerateRequest,
    WorldGenerateResponse,
    WorldOrigin,
    SystemDisplayType,
)
from app.world_visibility import ALLOWED_VISIBILITIES, normalize_visibility

router = APIRouter(
    prefix="/api/novels/{novel_id}/world",
    tags=["world"],
    dependencies=[Depends(verify_novel_access)],
)
WorldModelRowStatus = Literal["draft", "confirmed"]
_T = TypeVar("_T")


def _error_detail(code: str, message: str) -> dict[str, str]:
    # Frontend maps `code` to user-facing copy; `message` is for diagnostics only.
    return {"code": code, "message": message}


def _parse_visibility_filter(visibility: str | None) -> str | None:
    if visibility is None:
        return None
    normalized = normalize_visibility(visibility)
    if not isinstance(normalized, str):
        raise HTTPException(status_code=422, detail=_error_detail("invalid_visibility", "Invalid visibility"))
    if normalized not in ALLOWED_VISIBILITIES:
        raise HTTPException(status_code=422, detail=_error_detail("invalid_visibility", "Invalid visibility"))
    return normalized


def _translate_world_operation_error(exc: WorldCrudError | WorldUseCaseError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=_error_detail(exc.code, exc.message))


def _run_world_operation(operation: Callable[..., _T], /, *args, **kwargs) -> _T:
    try:
        return operation(*args, **kwargs)
    except (WorldCrudDetailError, WorldUseCaseDetailError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=getattr(exc, "headers", None),
        )
    except (WorldCrudError, WorldUseCaseError) as exc:
        raise _translate_world_operation_error(exc)


async def _run_world_operation_async(operation: Callable[..., object], /, *args, **kwargs):
    try:
        return await operation(*args, **kwargs)
    except (WorldCrudDetailError, WorldUseCaseDetailError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=getattr(exc, "headers", None),
        )
    except (WorldCrudError, WorldUseCaseError) as exc:
        raise _translate_world_operation_error(exc)


def _get_novel(novel_id: int, db: Session) -> Novel:
    return _run_world_operation(load_novel, novel_id, db)


def _get_entity(novel_id: int, entity_id: int, db: Session) -> WorldEntity:
    return _run_world_operation(load_entity, novel_id, entity_id, db)


def _get_relationship(novel_id: int, relationship_id: int, db: Session) -> WorldRelationship:
    return _run_world_operation(load_relationship, novel_id, relationship_id, db)


def _get_system(novel_id: int, system_id: int, db: Session) -> WorldSystem:
    return _run_world_operation(load_system, novel_id, system_id, db)




def _translate_worldpack_import_error(exc: WorldpackImportError) -> HTTPException:
    if isinstance(exc, WorldpackNovelNotFoundError):
        status_code = 404
    elif isinstance(exc, UnsupportedWorldpackSchemaVersionError):
        status_code = 400
    elif isinstance(exc, WorldpackImportConflictError):
        status_code = 409
    else:
        status_code = 400
    return HTTPException(status_code=status_code, detail=_error_detail(exc.code, exc.message))


def _serialize_worldpack_import_result(result: WorldpackImportResult) -> WorldpackImportResponse:
    return WorldpackImportResponse(
        pack_id=result.pack_id,
        counts=WorldpackImportCounts(**asdict(result.counts)),
        warnings=[WorldpackImportWarning(**asdict(warning)) for warning in result.warnings],
    )


def _serialize_bootstrap_job(job: BootstrapJob) -> BootstrapJobResponse:
    progress = job.progress or {}
    result = job.result or {}
    mode = BootstrapMode(resolve_bootstrap_mode(getattr(job, "mode", None)))
    return BootstrapJobResponse(
        job_id=job.id,
        novel_id=job.novel_id,
        mode=mode,
        initialized=is_bootstrap_initialized(job),
        status=job.status,
        progress=BootstrapProgress(
            step=int(progress.get("step", 0)),
            detail=str(progress.get("detail", "")),
        ),
        result=BootstrapResult(
            entities_found=int(result.get("entities_found", 0)),
            relationships_found=int(result.get("relationships_found", 0)),
            index_refresh_only=bool(result.get("index_refresh_only", False)),
        ),
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


# ===========================================================================
# Entities
# ===========================================================================


@router.get("/entities", response_model=List[WorldEntityResponse])
def list_entities(
    novel_id: int,
    q: Optional[str] = None,
    entity_type: Optional[str] = None,
    origin: Optional[WorldOrigin] = None,
    worldpack_pack_id: Optional[str] = None,
    worldpack_key: Optional[str] = None,
    status: Optional[WorldModelRowStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    query = db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id)
    if q:
        needle = q.strip()
        if needle:
            like = f"%{needle}%"
            query = query.filter(or_(WorldEntity.name.ilike(like), WorldEntity.description.ilike(like)))
    if entity_type:
        query = query.filter(WorldEntity.entity_type == entity_type)
    if origin:
        query = query.filter(WorldEntity.origin == origin)
    if worldpack_pack_id:
        query = query.filter(WorldEntity.worldpack_pack_id == worldpack_pack_id)
    if worldpack_key:
        query = query.filter(WorldEntity.worldpack_key == worldpack_key)
    if status:
        query = query.filter(WorldEntity.status == status)
    return query.order_by(WorldEntity.id.asc()).all()


@router.post("/entities", response_model=WorldEntityResponse, status_code=201)
def create_entity(
    novel_id: int,
    body: WorldEntityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    entity = _run_world_operation(
        create_entity_use_case,
        novel_id,
        body.model_dump(),
        user_id=current_user.id,
        db=db,
    )
    return entity


@router.get("/entities/{entity_id}", response_model=WorldEntityDetailResponse)
def get_entity(
    novel_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    return _get_entity(novel_id, entity_id, db)


@router.put("/entities/{entity_id}", response_model=WorldEntityResponse)
def update_entity(
    novel_id: int,
    entity_id: int,
    body: WorldEntityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    entity = _run_world_operation(
        update_entity_use_case,
        novel_id,
        entity_id,
        body.model_dump(exclude_none=True),
        user_id=current_user.id,
        db=db,
    )
    return entity


@router.delete("/entities/{entity_id}")
def delete_entity(
    novel_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _run_world_operation(delete_entity_use_case, novel_id, entity_id, db=db)
    return {"message": "Entity deleted"}


@router.post("/entities/confirm", response_model=BatchConfirmResponse)
def batch_confirm_entities(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    count = _run_world_operation(confirm_entity_drafts, novel_id, body.ids, user_id=current_user.id, db=db)
    return BatchConfirmResponse(confirmed=count)


@router.post("/entities/reject", response_model=BatchRejectResponse)
def batch_reject_entities(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    count = _run_world_operation(reject_entity_drafts, novel_id, body.ids, user_id=current_user.id, db=db)
    return BatchRejectResponse(rejected=count)


# ===========================================================================
# Attributes
# ===========================================================================


@router.post("/entities/{entity_id}/attributes", response_model=WorldEntityAttributeResponse, status_code=201)
def add_attribute(
    novel_id: int,
    entity_id: int,
    body: WorldAttributeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    attr = _run_world_operation(create_attribute_use_case, novel_id, entity_id, body.model_dump(), db=db)
    return attr


@router.put("/entities/{entity_id}/attributes/{attribute_id}", response_model=WorldEntityAttributeResponse)
def update_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    body: WorldAttributeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    attr = _run_world_operation(
        update_attribute_use_case,
        novel_id,
        entity_id,
        attribute_id,
        body.model_dump(exclude_none=True),
        db=db,
    )
    return attr


@router.delete("/entities/{entity_id}/attributes/{attribute_id}")
def delete_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _run_world_operation(delete_attribute_use_case, novel_id, entity_id, attribute_id, db=db)
    return {"message": "Attribute deleted"}


@router.patch("/entities/{entity_id}/attributes/reorder")
def reorder_attributes(
    novel_id: int,
    entity_id: int,
    body: AttributeReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _run_world_operation(reorder_attribute_values, novel_id, entity_id, body.order, db=db)
    return {"message": "Reordered"}


# ===========================================================================
# Relationships
# ===========================================================================


@router.get("/relationships", response_model=List[WorldRelationshipResponse])
def list_relationships(
    novel_id: int,
    q: Optional[str] = None,
    entity_id: Optional[int] = None,
    source_id: Optional[int] = None,
    target_id: Optional[int] = None,
    origin: Optional[WorldOrigin] = None,
    worldpack_pack_id: Optional[str] = None,
    visibility: Optional[str] = None,
    status: Optional[WorldModelRowStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    query = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id)
    if q:
        needle = q.strip()
        if needle:
            like = f"%{needle}%"
            query = query.filter(or_(WorldRelationship.label.ilike(like), WorldRelationship.description.ilike(like)))
    if entity_id is not None:
        _get_entity(novel_id, entity_id, db)
        query = query.filter(
            or_(
                WorldRelationship.source_id == entity_id,
                WorldRelationship.target_id == entity_id,
            )
        )
    if source_id is not None:
        _get_entity(novel_id, source_id, db)
        query = query.filter(WorldRelationship.source_id == source_id)
    if target_id is not None:
        _get_entity(novel_id, target_id, db)
        query = query.filter(WorldRelationship.target_id == target_id)
    if origin:
        query = query.filter(WorldRelationship.origin == origin)
    if worldpack_pack_id:
        query = query.filter(WorldRelationship.worldpack_pack_id == worldpack_pack_id)
    visibility = _parse_visibility_filter(visibility)
    if visibility:
        query = query.filter(WorldRelationship.visibility == visibility)
    if status:
        query = query.filter(WorldRelationship.status == status)
    return query.order_by(WorldRelationship.id.asc()).all()


@router.post("/relationships", response_model=WorldRelationshipResponse, status_code=201)
def create_relationship(
    novel_id: int,
    body: WorldRelationshipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    rel = _run_world_operation(
        create_relationship_use_case,
        novel_id,
        body.model_dump(),
        user_id=current_user.id,
        db=db,
    )
    return rel


@router.put("/relationships/{relationship_id}", response_model=WorldRelationshipResponse)
def update_relationship(
    novel_id: int,
    relationship_id: int,
    body: WorldRelationshipUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    rel = _run_world_operation(
        update_relationship_use_case,
        novel_id,
        relationship_id,
        body.model_dump(exclude_none=True),
        user_id=current_user.id,
        db=db,
    )
    return rel

@router.delete("/relationships/{relationship_id}")
def delete_relationship(
    novel_id: int,
    relationship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _run_world_operation(delete_relationship_use_case, novel_id, relationship_id, db=db)
    return {"message": "Relationship deleted"}


@router.post("/relationships/confirm", response_model=BatchConfirmResponse)
def batch_confirm_relationships(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    count = _run_world_operation(confirm_relationship_drafts, novel_id, body.ids, user_id=current_user.id, db=db)
    return BatchConfirmResponse(confirmed=count)


@router.post("/relationships/reject", response_model=BatchRejectResponse)
def batch_reject_relationships(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    count = _run_world_operation(reject_relationship_drafts, novel_id, body.ids, user_id=current_user.id, db=db)
    return BatchRejectResponse(rejected=count)


# ===========================================================================
# Systems
# ===========================================================================


@router.get("/systems", response_model=List[WorldSystemResponse])
def list_systems(
    novel_id: int,
    q: Optional[str] = None,
    origin: Optional[WorldOrigin] = None,
    worldpack_pack_id: Optional[str] = None,
    visibility: Optional[str] = None,
    status: Optional[WorldModelRowStatus] = None,
    display_type: Optional[SystemDisplayType] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    query = db.query(WorldSystem).filter(WorldSystem.novel_id == novel_id)
    if q:
        needle = q.strip()
        if needle:
            like = f"%{needle}%"
            query = query.filter(or_(WorldSystem.name.ilike(like), WorldSystem.description.ilike(like)))
    if origin:
        query = query.filter(WorldSystem.origin == origin)
    if worldpack_pack_id:
        query = query.filter(WorldSystem.worldpack_pack_id == worldpack_pack_id)
    visibility = _parse_visibility_filter(visibility)
    if visibility:
        query = query.filter(WorldSystem.visibility == visibility)
    if status:
        query = query.filter(WorldSystem.status == status)
    if display_type:
        query = query.filter(WorldSystem.display_type == display_type)
    return query.order_by(WorldSystem.id.asc()).all()


@router.post("/systems", response_model=WorldSystemResponse, status_code=201)
def create_system(
    novel_id: int,
    body: WorldSystemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    system = _run_world_operation(
        create_system_use_case,
        novel_id,
        body.model_dump(),
        user_id=current_user.id,
        db=db,
    )
    return system


@router.get("/systems/{system_id}", response_model=WorldSystemResponse)
def get_system(
    novel_id: int,
    system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    return _get_system(novel_id, system_id, db)


@router.put("/systems/{system_id}", response_model=WorldSystemResponse)
def update_system(
    novel_id: int,
    system_id: int,
    body: WorldSystemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    system = _run_world_operation(
        update_system_use_case,
        novel_id,
        system_id,
        body.model_dump(exclude_none=True),
        user_id=current_user.id,
        db=db,
    )
    return system


@router.delete("/systems/{system_id}")
def delete_system(
    novel_id: int,
    system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _run_world_operation(delete_system_use_case, novel_id, system_id, db=db)
    return {"message": "System deleted"}


@router.post("/systems/confirm", response_model=BatchConfirmResponse)
def batch_confirm_systems(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    count = _run_world_operation(confirm_system_drafts, novel_id, body.ids, user_id=current_user.id, db=db)
    return BatchConfirmResponse(confirmed=count)


@router.post("/systems/reject", response_model=BatchRejectResponse)
def batch_reject_systems(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    count = _run_world_operation(reject_system_drafts, novel_id, body.ids, user_id=current_user.id, db=db)
    return BatchRejectResponse(rejected=count)


# ===========================================================================
# Worldpack Import
# ===========================================================================

@router.post("/worldpack/import", response_model=WorldpackImportResponse)
def import_worldpack_v1(
    novel_id: int,
    body: WorldpackV1Payload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _ = current_user
    try:
        result = import_worldpack_payload(novel_id=novel_id, body=body, db=db)
    except WorldpackImportError as exc:
        raise _translate_worldpack_import_error(exc)
    return _serialize_worldpack_import_result(result)



# ===========================================================================
# World Generation
# ===========================================================================


@router.post("/generate", response_model=WorldGenerateResponse)
async def generate_world_from_text(
    novel_id: int,
    body: WorldGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: dict | None = Depends(get_llm_config),
    _quota_user: User = Depends(check_generation_quota),
):
    return await _run_world_operation_async(
        generate_world_from_text_use_case,
        novel_id,
        text=body.text,
        db=db,
        current_user=current_user,
        llm_config=llm_config,
        request_id=getattr(getattr(request, "state", None), "request_id", None),
    )


# ===========================================================================
# Bootstrap
# ===========================================================================


@router.post("/bootstrap", response_model=BootstrapJobResponse, status_code=202)
async def trigger_bootstrap(
    novel_id: int,
    llm_config: dict | None = Depends(get_llm_config),
    body: BootstrapTriggerRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    _quota_user: User = Depends(check_generation_quota),
):
    job = await _run_world_operation_async(
        trigger_bootstrap_use_case,
        novel_id,
        body=body,
        db=db,
        current_user=current_user,
        llm_config=llm_config,
        settings=get_settings(),
    )
    return _serialize_bootstrap_job(job)


@router.get("/bootstrap/status", response_model=BootstrapJobResponse)
def get_bootstrap_status(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _ = current_user
    job = _run_world_operation(get_bootstrap_status_use_case, novel_id, db=db, settings=get_settings())
    return _serialize_bootstrap_job(job)
