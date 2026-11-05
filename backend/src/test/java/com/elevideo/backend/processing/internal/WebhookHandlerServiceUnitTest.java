package com.elevideo.backend.processing.internal;

import com.elevideo.backend.processing.api.dto.webhook.ProcessingJobWebhookRequest;
import com.elevideo.backend.processing.api.dto.webhook.ProgressWebhookRequest;
import com.elevideo.backend.processing.internal.event.VideoProcessingCompletedEvent;
import com.elevideo.backend.processing.internal.mapper.ProcessingJobMapper;
import com.elevideo.backend.processing.internal.mapper.VideoRenditionMapper;
import com.elevideo.backend.processing.internal.model.JobStatus;
import com.elevideo.backend.processing.internal.model.ProcessingJob;
import com.elevideo.backend.processing.internal.model.ProcessingMode;
import com.elevideo.backend.processing.internal.model.VideoRendition;
import com.elevideo.backend.processing.internal.repository.ProcessingJobRepository;
import com.elevideo.backend.processing.internal.repository.VideoRenditionRepository;
import com.elevideo.backend.shared.event.DomainEventPublisher;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class WebhookHandlerServiceUnitTest {

    @Mock private ProcessingJobRepository jobs;
    @Mock private VideoRenditionRepository renditions;
    @Mock private ProcessingJobMapper jobMapper;
    @Mock private VideoRenditionMapper renditionMapper;
    @Mock private DomainEventPublisher events;

    private WebhookHandlerService service;

    @BeforeEach
    void setUp() {
        service = new WebhookHandlerService(jobs, renditions, jobMapper, renditionMapper, events);
    }

    @ParameterizedTest
    @EnumSource(value = JobStatus.class, names = {"COMPLETED", "FAILED", "CANCELLED"})
    void lateProgressCannotMutateTerminalJobs(JobStatus terminalStatus) {
        ProcessingJob job = job("job-42", terminalStatus);
        job.setProgressPercent(100);
        when(jobs.findByJobId("job-42")).thenReturn(Optional.of(job));

        service.handleProgressUpdate(progress("job-42", "processing", 25));

        assertEquals(terminalStatus, job.getStatus());
        assertEquals(100, job.getProgressPercent());
        verify(jobs, never()).save(any());
        verifyNoInteractions(renditions, jobMapper, renditionMapper, events);
    }

    @Test
    void activeJobPersistsProgressPhaseAndEta() {
        ProcessingJob job = job("job-42", JobStatus.PENDING);
        when(jobs.findByJobId("job-42")).thenReturn(Optional.of(job));
        ProgressWebhookRequest request = progress("job-42", "processing", 45);

        service.handleProgressUpdate(request);

        assertEquals(JobStatus.PROCESSING, job.getStatus());
        assertEquals(45, job.getProgressPercent());
        assertEquals("rendering", job.getPhase());
        assertEquals(30, job.getEtaSeconds());
        assertEquals("Procesando", job.getMessage());
        verify(jobs).save(job);
        verifyNoInteractions(renditions, jobMapper, renditionMapper, events);
    }

    @Test
    void unknownJobDoesNotCreateAnySideEffects() {
        when(jobs.findByJobId("missing")).thenReturn(Optional.empty());

        assertThrows(IllegalArgumentException.class,
                () -> service.handleProgressUpdate(progress("missing", "processing", 10)));

        verify(jobs, never()).save(any());
        verifyNoInteractions(renditions, jobMapper, renditionMapper, events);
    }

    @Test
    void completionPersistsRenditionAndPublishesDomainEvent() {
        ProcessingJob job = job("job-42", JobStatus.PROCESSING);
        job.setVideoId(7L);
        VideoRendition rendition = new VideoRendition();
        ProcessingJobWebhookRequest request = completion(JobStatus.COMPLETED);
        when(jobs.findByJobId("job-42")).thenReturn(Optional.of(job));
        when(renditionMapper.toVideoRendition(request)).thenReturn(rendition);
        when(renditions.save(rendition)).thenReturn(rendition);

        service.handleJobCompleted(request);

        assertEquals(100, job.getProgressPercent());
        assertSame(rendition, job.getVideoRendition());
        assertEquals(7L, rendition.getVideoId());
        assertEquals(job.getProcessingMode(), rendition.getProcessingMode());
        verify(jobMapper).updateFromWebhook(request, job);
        verify(renditions).save(rendition);
        verify(jobs).save(job);

        ArgumentCaptor<VideoProcessingCompletedEvent> event =
                ArgumentCaptor.forClass(VideoProcessingCompletedEvent.class);
        verify(events).publish(event.capture());
        assertEquals(7L, event.getValue().getVideoId());
        assertEquals("job-42", event.getValue().getJobId());
        assertEquals("https://example.invalid/output.mp4", event.getValue().getOutputUrl());
    }

    @Test
    void failureDoesNotPublishSuccessOrCreateRendition() {
        ProcessingJob job = job("job-42", JobStatus.PROCESSING);
        ProcessingJobWebhookRequest request = completion(JobStatus.FAILED);
        when(jobs.findByJobId("job-42")).thenReturn(Optional.of(job));

        service.handleJobCompleted(request);

        assertNull(job.getVideoRendition());
        verify(jobMapper).updateFromWebhook(request, job);
        verify(jobs).save(job);
        verifyNoInteractions(renditions, renditionMapper, events);
    }

    private static ProcessingJob job(String id, JobStatus status) {
        ProcessingJob job = new ProcessingJob();
        job.setJobId(id);
        job.setStatus(status);
        job.setProcessingMode(ProcessingMode.VERTICAL);
        return job;
    }

    private static ProgressWebhookRequest progress(String id, String status, int percentage) {
        ProgressWebhookRequest request = new ProgressWebhookRequest();
        request.setJobId(id);
        request.setStatus(status);
        request.setProgress(percentage);
        request.setPhase("rendering");
        request.setEtaSeconds(30);
        request.setMessage("Procesando");
        return request;
    }

    private static ProcessingJobWebhookRequest completion(JobStatus status) {
        return new ProcessingJobWebhookRequest(
                "job-42", status, ProcessingMode.VERTICAL, 12.0, "rendering", Instant.now(),
                "https://example.invalid/output.mp4", null, null, 0.95, 10.0,
                null, null, status == JobStatus.FAILED ? "failure" : null
        );
    }
}
