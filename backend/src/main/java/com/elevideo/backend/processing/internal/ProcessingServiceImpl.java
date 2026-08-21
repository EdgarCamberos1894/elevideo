package com.elevideo.backend.processing.internal;

import com.elevideo.backend.processing.api.ProcessingService;
import com.elevideo.backend.processing.api.dto.*;
import com.elevideo.backend.processing.internal.client.PythonServiceClient;
import com.elevideo.backend.processing.internal.client.VideoPythonRequest;
import com.elevideo.backend.processing.internal.mapper.ProcessingJobMapper;
import com.elevideo.backend.processing.internal.mapper.VideoProcessingMapper;
import com.elevideo.backend.processing.internal.mapper.VideoRenditionMapper;
import com.elevideo.backend.processing.internal.model.JobLifecycleGroup;
import com.elevideo.backend.processing.internal.model.JobStatus;
import com.elevideo.backend.processing.internal.model.PlatformShortLimits;
import com.elevideo.backend.processing.internal.model.ProcessingJob;
import com.elevideo.backend.processing.internal.model.ProcessingMode;
import com.elevideo.backend.processing.internal.model.ShortAutoDurationMode;
import com.elevideo.backend.processing.internal.model.VideoRendition;
import com.elevideo.backend.processing.internal.repository.ProcessingJobRepository;
import com.elevideo.backend.processing.internal.repository.VideoRenditionRepository;
import com.elevideo.backend.processing.internal.spec.ProcessingJobSpecification;
import com.elevideo.backend.processing.internal.spec.VideoRenditionSpecification;
import com.elevideo.backend.shared.exception.base.ConflictException;
import com.elevideo.backend.shared.exception.base.NotFoundException;
import com.elevideo.backend.shared.security.CurrentUserProvider;
import com.elevideo.backend.video.api.VideoService;
import com.elevideo.backend.video.api.dto.VideoResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
class ProcessingServiceImpl implements ProcessingService {

    private static final int MIN_SHORT_DURATION_SECONDS = 5;

    private final ProcessingJobRepository  jobRepository;
    private final VideoRenditionRepository renditionRepository;
    private final ProcessingJobMapper      jobMapper;
    private final VideoProcessingMapper    processingMapper;
    private final VideoRenditionMapper     renditionMapper;
    private final PythonServiceClient      pythonClient;
    private final VideoService             videoService;
    private final CurrentUserProvider      currentUserProvider;

    @Value("${app.processing.guardrails.max-input-duration-seconds:1800}")
    private long maxInputDurationSeconds;

    @Override
    @Transactional
    public VideoJobCreatedResponse processVideo(Long videoId, VideoProcessRequest request, String baseUrl) {
        assertVideoAccess(videoId);

        UUID userId = currentUserProvider.getCurrentUserId();
        VideoResponse video = videoService.getVideoById(videoId);
        validateDemoInputDuration(video);
        validateClipRange(request, video);
        VideoPythonRequest pythonRequest = processingMapper.toVideoPythonRequest(request, video.videoUrl());

        VideoJobCreatedResponse pythonResponse = pythonClient.post(
                "/api/video/process", pythonRequest, VideoJobCreatedResponse.class, userId
        );

        ProcessingJob job = jobMapper.toProcessingJob(request, pythonResponse);
        job.setVideoId(videoId);
        jobRepository.save(job);

        String statusUrl = baseUrl + "/jobs/" + pythonResponse.jobId();

        return new VideoJobCreatedResponse(
                pythonResponse.jobId(),
                pythonResponse.status(),
                pythonResponse.processingMode(),
                statusUrl
        );
    }

    @Override
    @Transactional
    public JobResponse getJobStatus(Long videoId, String jobId) {
        assertVideoAccess(videoId);
        UUID userId = currentUserProvider.getCurrentUserId();
        ProcessingJob job = findJob(jobId, videoId);

        VideoJobStatusResponse pythonResponse = pythonClient.get(
                "/api/video/status/" + jobId, VideoJobStatusResponse.class, userId
        );

        job.setProgressPercent(pythonResponse.progress());
        job.setStatus(JobStatus.fromValue(pythonResponse.status()));
        job.setPhase(pythonResponse.phase());
        jobRepository.save(job);

        JobResponse fromPython = jobMapper.toJobResponse(pythonResponse);

        return new JobResponse(
                fromPython.jobId(),
                fromPython.status(),
                fromPython.progress(),
                fromPython.phase(),
                job.getProcessingMode(),
                job.getPlatform(),
                job.getBackgroundMode(),
                job.getQuality(),
                fromPython.output(),
                fromPython.errorDetail(),
                job.getCreatedAt()
        );
    }

    @Override
    public VideoJobCancelResponse cancelJob(Long videoId, String jobId) {
        assertVideoAccess(videoId);
        UUID userId = currentUserProvider.getCurrentUserId();
        return pythonClient.postEmpty(
                "/api/video/jobs/" + jobId + "/cancel", VideoJobCancelResponse.class, userId
        );
    }

    @Override
    @Transactional(readOnly = true)
    public Page<VideoRenditionResponse> getRenditions(Long videoId, VideoRenditionSearchRequest request) {
        assertVideoAccess(videoId);

        Specification<VideoRendition> spec = VideoRenditionSpecification.belongsToVideo(videoId);

        if (request.processingMode() != null)
            spec = spec.and(VideoRenditionSpecification.hasProcessingMode(request.processingMode()));
        if (request.platform() != null)
            spec = spec.and(VideoRenditionSpecification.hasPlatform(request.platform()));
        if (request.backgroundMode() != null)
            spec = spec.and(VideoRenditionSpecification.hasBackgroundMode(request.backgroundMode()));

        return renditionRepository.findAll(spec, request.toPageable())
                .map(renditionMapper::toVideoRenditionResponse);
    }

    @Override
    @Transactional(readOnly = true)
    public VideoRenditionResponse getRenditionById(Long videoId, Long renditionId) {
        assertVideoAccess(videoId);
        VideoRendition rendition = renditionRepository.findByIdAndVideoId(renditionId, videoId)
                .orElseThrow(() -> new RenditionNotFoundException(renditionId));
        return renditionMapper.toVideoRenditionResponse(rendition);
    }

    @Override
    @Transactional
    public void deleteRendition(Long videoId, Long renditionId) {
        assertVideoAccess(videoId);
        VideoRendition rendition = renditionRepository.findByIdAndVideoId(renditionId, videoId)
                .orElseThrow(() -> new RenditionNotFoundException(renditionId));

        jobRepository.findByVideoRenditionId(renditionId)
                .ifPresent(job -> {
                    job.setVideoRendition(null);
                    jobRepository.save(job);
                });

        renditionRepository.delete(rendition);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<JobResponse> listJobs(Long videoId, JobSearchRequest request) {
        assertVideoAccess(videoId);

        Specification<ProcessingJob> spec = Specification.allOf(
                ProcessingJobSpecification.belongsToVideo(videoId),
                ProcessingJobSpecification.hasStatusIn(request.status()),
                ProcessingJobSpecification.hasProcessingMode(request.processingMode()),
                ProcessingJobSpecification.hasPlatform(request.platform()),
                ProcessingJobSpecification.hasBackgroundMode(request.backgroundMode())
        );

        return jobRepository.findAll(spec, request.toPageable())
                .map(jobMapper::toJobResponse);
    }

    @Override
    @Transactional(readOnly = true)
    public JobOverviewResponse getOverview(Long videoId) {
        assertVideoAccess(videoId);

        Specification<ProcessingJob> base = ProcessingJobSpecification.belongsToVideo(videoId);

        List<JobResponse> active = jobRepository
                .findAll(base.and(ProcessingJobSpecification.hasLifecycleGroup(JobLifecycleGroup.ACTIVE)),
                        PageRequest.of(0, 50, Sort.by(Sort.Direction.DESC, "createdAt")))
                .stream().map(jobMapper::toJobResponse).toList();

        List<JobResponse> finished = jobRepository
                .findAll(base.and(ProcessingJobSpecification.hasLifecycleGroup(JobLifecycleGroup.FINISHED)),
                        PageRequest.of(0, 10, Sort.by(Sort.Direction.DESC, "createdAt")))
                .stream().map(jobMapper::toJobResponse).toList();

        return new JobOverviewResponse(active, finished);
    }

    private void assertVideoAccess(Long videoId) {
        UUID userId = currentUserProvider.getCurrentUserId();
        videoService.assertVideoOwnedByUser(videoId, userId);
    }

    private void validateDemoInputDuration(VideoResponse video) {
        Long durationInSeconds = video.durationInSeconds();
        if (durationInSeconds == null || durationInSeconds <= 0 || maxInputDurationSeconds <= 0) {
            return;
        }
        if (durationInSeconds > maxInputDurationSeconds) {
            long maxMinutes = Math.max(1, maxInputDurationSeconds / 60);
            throw new InvalidClipRangeException(
                    "Para proteger los recursos del demo, el video fuente no puede superar "
                            + maxMinutes + " minutos."
            );
        }
    }

    private void validateClipRange(VideoProcessRequest request, VideoResponse video) {
        if (request.processingMode() == null || request.processingMode() == ProcessingMode.VERTICAL) {
            return;
        }

        Long durationInSeconds = video.durationInSeconds();
        if (durationInSeconds == null || durationInSeconds <= 0) {
            throw new InvalidClipRangeException("No se pudo determinar la duración del video para crear el short.");
        }

        if (durationInSeconds < MIN_SHORT_DURATION_SECONDS) {
            throw new InvalidClipRangeException(
                    "El video debe durar al menos " + MIN_SHORT_DURATION_SECONDS + " segundos para crear un short."
            );
        }

        double videoDuration = durationInSeconds.doubleValue();
        int platformMaxDuration = PlatformShortLimits.maxDurationSeconds(request.platform());

        if (request.processingMode() == ProcessingMode.SHORT_AUTO) {
            ShortAutoDurationMode durationMode = request.shortAutoDurationMode() == null
                    ? ShortAutoDurationMode.EXACT
                    : request.shortAutoDurationMode();
            Integer requestedDuration = request.shortAutoDuration();

            if (durationMode != ShortAutoDurationMode.AUTO && requestedDuration == null) {
                throw new InvalidClipRangeException(
                        "Debes indicar la duración objetivo cuando el modo es aproximado o exacto."
                );
            }
            if (requestedDuration != null && requestedDuration > platformMaxDuration) {
                throw new InvalidClipRangeException(
                        "La duración objetivo no puede superar los " + platformMaxDuration
                                + " segundos para la plataforma seleccionada."
                );
            }
            if (
                    durationMode != ShortAutoDurationMode.AUTO
                            && requestedDuration != null
                            && requestedDuration > videoDuration
            ) {
                throw new InvalidClipRangeException(
                        "La duración objetivo no puede superar los " + durationInSeconds + " segundos del video."
                );
            }
            return;
        }

        if (request.processingMode() == ProcessingMode.SHORT_MANUAL) {
            VideoProcessRequest.ShortManualOptions options = request.shortOptions();
            if (options == null) {
                throw new InvalidClipRangeException("Debes indicar el inicio y la duración del short manual.");
            }
            if (options.duration() > platformMaxDuration) {
                throw new InvalidClipRangeException(
                        "La duración del clip no puede superar los " + platformMaxDuration
                                + " segundos para la plataforma seleccionada."
                );
            }

            double clipEnd = options.startTime() + options.duration();
            if (clipEnd > videoDuration + 0.001d) {
                throw new InvalidClipRangeException(
                        "El corte manual termina después del final del video. Ajusta el inicio o la duración."
                );
            }
        }
    }

    private ProcessingJob findJob(String jobId, Long videoId) {
        return jobRepository.findByJobIdAndVideoId(jobId, videoId)
                .orElseThrow(() -> new JobNotFoundException(jobId));
    }

    static class JobNotFoundException extends NotFoundException {
        JobNotFoundException(String jobId) { super("Job not found: " + jobId); }
    }

    static class RenditionNotFoundException extends NotFoundException {
        RenditionNotFoundException(Long id) { super("Rendition not found with id: " + id); }
    }

    static class InvalidClipRangeException extends ConflictException {
        InvalidClipRangeException(String message) { super(message); }
    }
}
