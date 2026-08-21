import logging
import uuid
from datetime import datetime
from threading import Lock
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from models.schemas import (
    VideoProcessRequest,
    VideoProcessResponse,
    JobStatusResponse,
    JobStatus,
    ProcessingMode,
)
from services.video_service import VideoProcessingService
from storage.cloudinary_service import CloudinaryService
from utils.validators import validate_video_request
from core.exceptions import ValidationError, VideoProcessingError
from core.error_handler import ErrorHandler
from core.auth import TokenData, require_service_token, verify_job_ownership
from utils.cancellation_manager import get_cancellation_manager, JobCancelledException
from utils.job_dispatcher import BoundedJobDispatcher
from utils.processing_guardrails import (
    GuardrailRejected,
    ProcessingGuardrails,
    ProcessingGuardrailSettings,
)
from services.webhook_service import notify_job_completed, notify_job_failed, notify_job_cancelled

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["Video"])

jobs_db: Dict[str, dict] = {}
idempotency_jobs: Dict[str, str] = {}
admission_lock = Lock()
cancellation_manager = get_cancellation_manager()

guardrail_settings = ProcessingGuardrailSettings.from_env()
guardrails = ProcessingGuardrails(guardrail_settings)
job_dispatcher: Optional[BoundedJobDispatcher] = None

cloudinary_service: CloudinaryService = None
video_service: VideoProcessingService = None


def set_services(cloudinary_svc: CloudinaryService, video_svc: VideoProcessingService) -> None:
    global cloudinary_service, video_service, job_dispatcher
    cloudinary_service = cloudinary_svc
    video_service = video_svc

    def _on_progress(job_id: str, data: dict) -> None:
        if job_id in jobs_db:
            jobs_db[job_id].update({
                "progress":        data.get("progress", 0),
                "message":         data.get("message", ""),
                "phase":           data.get("phase"),
                "elapsed_seconds": data.get("elapsed_seconds"),
                "eta_seconds":     data.get("eta_seconds"),
                "eta_formatted":   data.get("eta_formatted"),
            })

    video_service.set_progress_callback(_on_progress)

    if job_dispatcher is None:
        job_dispatcher = BoundedJobDispatcher(
            process_video_task,
            max_workers=guardrail_settings.max_concurrent_jobs,
            max_queue_size=guardrail_settings.max_queue_size,
        )
        logger.info(
            "Dispatcher de procesamiento listo | workers=%s | queue=%s",
            guardrail_settings.max_concurrent_jobs,
            guardrail_settings.max_queue_size,
        )


def _fail_job(job_id: str, user_message: str) -> None:
    job = jobs_db.get(job_id)
    if job is None:
        return
    job.update({
        "status":       JobStatus.failed,
        "message":      user_message,
        "error_detail": user_message,
        "progress":     job.get("progress", 0),
        "completed_at": datetime.utcnow(),
    })


def _idempotency_scope(user_id: str, key: str) -> str:
    return f"{user_id}:{key.strip()}"


def _created_response(job: dict) -> VideoProcessResponse:
    return VideoProcessResponse(
        job_id=job["job_id"],
        status=job["status"],
        message=job["message"],
        processing_mode=job["processing_mode"],
    )


def _new_job_record(
    job_id: str,
    token: TokenData,
    request: VideoProcessRequest,
    video_info: dict,
    idempotency_scope: Optional[str],
) -> dict:
    return {
        "job_id":                  job_id,
        "user_id":                 token.user_id,
        "status":                  JobStatus.pending,
        "message":                 "El video está en cola para procesarse",
        "processing_mode":         request.processing_mode,
        "progress":                0,
        "output_url":              None,
        "thumbnail_url":           None,
        "preview_url":             None,
        "quality_score":           None,
        "error_detail":            None,
        "segment_start":           None,
        "segment_duration":        None,
        "output_duration_seconds": None,
        "created_at":              datetime.utcnow(),
        "completed_at":            None,
        "request":                 request.model_dump(),
        "video_info":              video_info,
        "idempotency_scope":       idempotency_scope,
    }


def _remove_job(job_id: str) -> None:
    job = jobs_db.pop(job_id, None)
    if not job:
        return
    scope = job.get("idempotency_scope")
    if scope and idempotency_jobs.get(scope) == job_id:
        idempotency_jobs.pop(scope, None)


def process_video_task(job_id: str, request: VideoProcessRequest) -> None:
    job = jobs_db.get(job_id)
    if job is None:
        logger.info("Job omitido porque ya no existe | job_id=%s", job_id)
        return
    if job.get("status") == JobStatus.cancelled:
        logger.info("Job omitido porque fue cancelado en cola | job_id=%s", job_id)
        return

    try:
        logger.info("Job iniciado | job_id=%s | mode=%s", job_id, request.processing_mode.value)

        job.update({
            "status": JobStatus.processing,
            "message": "Procesando el video...",
            "progress": max(1, int(job.get("progress") or 0)),
        })

        output_url, metrics = video_service.process_video(request, job_id)

        job = jobs_db.get(job_id)
        if job is None:
            logger.warning("Job terminó pero fue eliminado del registro | job_id=%s", job_id)
            return

        job.update({
            "status":                  JobStatus.completed,
            "message":                 "Video procesado exitosamente",
            "progress":                100,
            "output_url":              output_url,
            "thumbnail_url":           metrics.get("thumbnail_url"),
            "preview_url":             metrics.get("preview_url"),
            "quality_score":           metrics.get("overall_quality"),
            "segment_start":           metrics.get("segment_start"),
            "segment_duration":        metrics.get("segment_duration"),
            "output_duration_seconds": metrics.get("output_duration_seconds"),
            "completed_at":            datetime.utcnow(),
        })

        logger.info("Job completado | job_id=%s | url=%s", job_id, output_url)
        notify_job_completed(job_id=job_id, output_url=output_url, metrics=metrics, job_data=job)

    except JobCancelledException:
        job = jobs_db.get(job_id)
        if job is None:
            return
        job.update({
            "status":       JobStatus.cancelled,
            "message":      "Procesamiento cancelado por el usuario",
            "completed_at": datetime.utcnow(),
        })
        logger.info("Job cancelado | job_id=%s", job_id)
        notify_job_cancelled(job_id=job_id, job_data=job)

    except VideoProcessingError as e:
        error_info = ErrorHandler.handle(e, job_id=job_id, operation="background_task")
        _fail_job(job_id, error_info["user_message"])
        logger.error("Job falló | job_id=%s | error=%s", job_id, error_info["user_message"])
        job = jobs_db.get(job_id)
        if job is not None:
            notify_job_failed(job_id=job_id, error_message=error_info["user_message"], job_data=job)

    except Exception as e:
        error_info = ErrorHandler.handle(e, job_id=job_id, operation="background_task")
        _fail_job(job_id, error_info["user_message"])
        logger.exception("Job falló con error inesperado | job_id=%s", job_id)
        job = jobs_db.get(job_id)
        if job is not None:
            notify_job_failed(job_id=job_id, error_message=error_info["user_message"], job_data=job)


_PROCESS_EXAMPLES = {
    "vertical": {
        "summary": "Video completo a 9:16",
        "value": {
            "processing_mode": "vertical", "platform": "tiktok",
            "background_mode": "smart_crop", "quality": "normal",
            "cloudinary_input_url": "https://res.cloudinary.com/demo/video/upload/sample.mp4",
        },
    },
    "short_auto": {
        "summary": "Short automático — segmento central",
        "value": {
            "processing_mode": "short_auto", "platform": "tiktok",
            "background_mode": "smart_crop", "quality": "normal",
            "short_auto_duration": 30,
            "cloudinary_input_url": "https://res.cloudinary.com/demo/video/upload/sample.mp4",
        },
    },
    "short_manual": {
        "summary": "Short manual — segmento exacto",
        "value": {
            "processing_mode": "short_manual", "platform": "instagram",
            "background_mode": "smart_crop", "quality": "high",
            "short_options": {"start_time": 45.0, "duration": 30},
            "cloudinary_input_url": "https://res.cloudinary.com/demo/video/upload/sample.mp4",
        },
    },
}

_ERRORS = {
    401: {"description": "Token ausente o inválido"},
    403: {"description": "Job pertenece a otro usuario"},
    404: {"description": "Job no encontrado"},
}


@router.post(
    "/process",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear job de procesamiento",
    responses={
        400: {"description": "Request inválido"},
        409: {"description": "Idempotency-Key reutilizada con otro request"},
        429: {"description": "Protección antiabuso activada"},
        503: {"description": "Cola global temporalmente llena"},
        **_ERRORS,
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"examples": _PROCESS_EXAMPLES}},
        }
    },
)
async def process_video(
    request: VideoProcessRequest,
    token: TokenData = Depends(require_service_token),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    try:
        video_info = validate_video_request(request)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logger.exception("Error inesperado durante validación")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al validar el request")

    request_data = request.model_dump()
    scope = _idempotency_scope(str(token.user_id), idempotency_key) if idempotency_key and idempotency_key.strip() else None

    with admission_lock:
        removed = guardrails.cleanup_finished_jobs(jobs_db, idempotency_jobs)
        if removed:
            logger.info("Jobs antiguos liberados de memoria | removed=%s", removed)

        if scope:
            existing_job_id = idempotency_jobs.get(scope)
            existing_job = jobs_db.get(existing_job_id) if existing_job_id else None
            if existing_job is not None:
                if existing_job.get("request") != request_data:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="La Idempotency-Key ya fue usada con una solicitud diferente.",
                    )
                logger.info(
                    "Job idempotente reutilizado | job_id=%s | user_id=%s",
                    existing_job_id,
                    token.user_id,
                )
                return _created_response(existing_job)
            if existing_job_id:
                idempotency_jobs.pop(scope, None)

        try:
            guardrails.assert_can_create(str(token.user_id), jobs_db.values())
        except GuardrailRejected as exc:
            logger.warning(
                "Solicitud bloqueada por guardrail | user_id=%s | status=%s | detail=%s",
                token.user_id,
                exc.status_code,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)

        if job_dispatcher is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El procesador todavía no está listo. Intenta nuevamente en un momento.",
            )

        job_id = str(uuid.uuid4())
        jobs_db[job_id] = _new_job_record(job_id, token, request, video_info, scope)
        if scope:
            idempotency_jobs[scope] = job_id

        if not job_dispatcher.submit(job_id, request):
            _remove_job(job_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="La cola de procesamiento está llena. Intenta nuevamente cuando termine algún video.",
            )

    logger.info(
        "Job creado | job_id=%s | user_id=%s | mode=%s | platform=%s | "
        "idempotent=%s | queue_depth=%s/%s",
        job_id,
        token.user_id,
        request.processing_mode.value,
        request.platform.value,
        bool(scope),
        job_dispatcher.queue_depth,
        job_dispatcher.capacity,
    )

    return _created_response(jobs_db[job_id])


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Consultar estado del job",
    responses=_ERRORS,
)
async def get_job_status(
    job_id: str,
    token: TokenData = Depends(require_service_token),
):
    job = jobs_db.get(job_id)
    verify_job_ownership(job, token, job_id)

    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        message=job["message"],
        processing_mode=job.get("processing_mode"),
        progress=job.get("progress"),
        phase=job.get("phase"),
        elapsed_seconds=job.get("elapsed_seconds"),
        eta_seconds=job.get("eta_seconds"),
        eta_formatted=job.get("eta_formatted"),
        output_url=job.get("output_url"),
        thumbnail_url=job.get("thumbnail_url"),
        preview_url=job.get("preview_url"),
        quality_score=job.get("quality_score"),
        segment_start=job.get("segment_start"),
        segment_duration=job.get("segment_duration"),
        output_duration_seconds=job.get("output_duration_seconds"),
        error_detail=job.get("error_detail"),
        created_at=job.get("created_at"),
        completed_at=job.get("completed_at"),
    )


@router.get(
    "/download/{job_id}",
    summary="Obtener URL de descarga",
    responses={
        400: {"description": "Video aún no disponible"},
        **_ERRORS,
    },
)
async def download_video(
    job_id: str,
    token: TokenData = Depends(require_service_token),
):
    job = jobs_db.get(job_id)
    verify_job_ownership(job, token, job_id)

    if job["status"] != JobStatus.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El video no está listo para descarga")

    return {
        "job_id":           job_id,
        "status":           "completed",
        "processing_mode":  job.get("processing_mode"),
        "video_url":        job["output_url"],
        "quality_score":    job.get("quality_score"),
        "segment_start":    job.get("segment_start"),
        "segment_duration": job.get("segment_duration"),
    }


@router.post(
    "/jobs/{job_id}/cancel",
    summary="Cancelar job en proceso",
    responses={
        400: {"description": "Job no cancelable"},
        **_ERRORS,
    },
)
async def cancel_job(
    job_id: str,
    token: TokenData = Depends(require_service_token),
):
    job = jobs_db.get(job_id)
    verify_job_ownership(job, token, job_id)

    current_status = job["status"]
    if current_status in (JobStatus.completed, JobStatus.failed, JobStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El job ya está en estado '{current_status}' y no puede ser cancelado",
        )

    if current_status == JobStatus.pending:
        job.update({
            "status": JobStatus.cancelled,
            "message": "Procesamiento cancelado antes de comenzar",
            "completed_at": datetime.utcnow(),
        })
        logger.info("Job cancelado mientras estaba en cola | job_id=%s", job_id)
        notify_job_cancelled(job_id=job_id, job_data=job)
        return {
            "job_id":          job_id,
            "message":         "Job cancelado. No llegará a usar recursos de procesamiento.",
            "previous_status": current_status,
        }

    cancellation_manager.request_cancellation(job_id)
    job["message"] = "Cancelando procesamiento..."
    logger.info("Cancelación solicitada | job_id=%s | status=%s", job_id, current_status)

    return {
        "job_id":          job_id,
        "message":         "Cancelación solicitada. El procesamiento se detendrá pronto.",
        "previous_status": current_status,
    }


@router.get("/jobs", summary="Listar jobs del usuario", tags=["Utilidades"])
async def list_jobs(token: TokenData = Depends(require_service_token)):
    user_jobs = sorted(
        [
            {
                "job_id":          jid,
                "status":          data["status"],
                "processing_mode": data.get("processing_mode"),
                "created_at":      data["created_at"],
                "platform":        data["request"]["platform"],
                "quality":         data["request"]["quality"],
            }
            for jid, data in jobs_db.items()
            if data.get("user_id") == token.user_id
        ],
        key=lambda item: item["created_at"],
        reverse=True,
    )
    return {"total_jobs": len(user_jobs), "jobs": user_jobs}


@router.delete(
    "/jobs/{job_id}",
    summary="Eliminar job",
    tags=["Utilidades"],
    responses={
        404: {"description": "Job no encontrado"},
        409: {"description": "El job sigue activo"},
    },
)
async def delete_job(
    job_id: str,
    token: TokenData = Depends(require_service_token),
):
    job = jobs_db.get(job_id)
    verify_job_ownership(job, token, job_id)

    if job.get("status") in (JobStatus.pending, JobStatus.processing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancela el job antes de eliminarlo.",
        )

    with admission_lock:
        _remove_job(job_id)

    logger.info("Job eliminado | job_id=%s | user_id=%s", job_id, token.user_id)
    return {"message": f"Job {job_id} eliminado exitosamente"}
