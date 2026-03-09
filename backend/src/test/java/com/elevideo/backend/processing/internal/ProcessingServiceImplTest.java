package com.elevideo.backend.processing.internal;

import com.elevideo.backend.processing.api.dto.*;
import com.elevideo.backend.processing.internal.client.PythonServiceClient;
import com.elevideo.backend.processing.internal.mapper.ProcessingJobMapper;
import com.elevideo.backend.processing.internal.mapper.VideoProcessingMapper;
import com.elevideo.backend.processing.internal.mapper.VideoRenditionMapper;
import com.elevideo.backend.processing.internal.model.*;
import com.elevideo.backend.processing.internal.repository.ProcessingJobRepository;
import com.elevideo.backend.processing.internal.repository.VideoRenditionRepository;
import com.elevideo.backend.shared.exception.base.NotFoundException;
import com.elevideo.backend.shared.security.CurrentUserProvider;
import com.elevideo.backend.video.api.VideoService;
import com.elevideo.backend.video.api.dto.VideoSummaryResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.BDDMockito.*;

@ExtendWith(MockitoExtension.class)
@DisplayName("ProcessingServiceImpl")
class ProcessingServiceImplTest {

    @Mock ProcessingJobRepository  jobRepository;
    @Mock VideoRenditionRepository renditionRepository;
    @Mock ProcessingJobMapper      jobMapper;
    @Mock VideoProcessingMapper    processingMapper;
    @Mock VideoRenditionMapper     renditionMapper;
    @Mock PythonServiceClient      pythonClient;
    @Mock VideoService             videoService;
    @Mock CurrentUserProvider      currentUserProvider;

    @InjectMocks ProcessingServiceImpl service;

    private static final UUID   USER_ID  = UUID.randomUUID();
    private static final Long   VIDEO_ID = 1L;
    private static final String JOB_ID   = "job-abc-123";

    // ----------------------------------------------------------------
    // processVideo
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("processVideo()")
    class ProcessVideo {

//        @Test
//        @DisplayName("should submit job to Python and persist ProcessingJob")
//        void shouldSubmitAndPersist() {
//            VideoProcessRequest request = buildProcessRequest();
//            VideoSummaryResponse videoSummary = buildVideoSummary();
//            VideoJobCreatedResponse pythonResponse = new VideoJobCreatedResponse(
//                    UUID.randomUUID(), JobStatus.PENDING, "Job queued", ProcessingMode.VERTICAL
//            );
//            ProcessingJob job = new ProcessingJob();
//
//            given(currentUserProvider.getCurrentUserId()).willReturn(USER_ID);
//            given(videoService.getVideoById(VIDEO_ID)).willReturn(videoSummary);
//            given(processingMapper.toVideoPythonRequest(any(), any())).willReturn(null);
//            given(pythonClient.post(any(), any(), eq(VideoJobCreatedResponse.class), eq(USER_ID)))
//                    .willReturn(pythonResponse);
//            given(jobMapper.toProcessingJob(request, pythonResponse)).willReturn(job);
//
//            VideoJobCreatedResponse result = service.processVideo(VIDEO_ID, request);
//
//            then(jobRepository).should().save(job);
//            assertThat(job.getVideoId()).isEqualTo(VIDEO_ID);
//            assertThat(result.status()).isEqualTo(JobStatus.PENDING);
//        }
    }

    // ----------------------------------------------------------------
    // getJobStatus
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("getJobStatus()")
    class GetJobStatus {

        @Test
        @DisplayName("should return job status and update local record")
        void shouldReturnAndUpdateStatus() {
            ProcessingJob job = buildJob();
            VideoJobStatusResponse statusResponse = buildStatusResponse();

            given(currentUserProvider.getCurrentUserId()).willReturn(USER_ID);
            given(jobRepository.findByJobIdAndVideoId(JOB_ID, VIDEO_ID)).willReturn(Optional.of(job));
            given(pythonClient.get(anyString(), eq(VideoJobStatusResponse.class), eq(USER_ID)))
                    .willReturn(statusResponse);
            given(jobMapper.toJobResponse(statusResponse)).willReturn(mock(JobResponse.class));

            service.getJobStatus(VIDEO_ID, JOB_ID);

            assertThat(job.getStatus()).isEqualTo(JobStatus.PROCESSING);
            assertThat(job.getProgressPercent()).isEqualTo(45);
            then(jobRepository).should().save(job);
        }

        @Test
        @DisplayName("should throw NotFoundException when job does not belong to video")
        void shouldThrowWhenJobNotFound() {
            given(currentUserProvider.getCurrentUserId()).willReturn(USER_ID);
            given(jobRepository.findByJobIdAndVideoId(JOB_ID, VIDEO_ID)).willReturn(Optional.empty());

            assertThatThrownBy(() -> service.getJobStatus(VIDEO_ID, JOB_ID))
                    .isInstanceOf(NotFoundException.class);
        }
    }

    // ----------------------------------------------------------------
    // deleteRendition
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("deleteRendition()")
    class DeleteRendition {

        @Test
        @DisplayName("should delete rendition when it belongs to video")
        void shouldDeleteWhenOwned() {
            VideoRendition rendition = new VideoRendition();
            given(renditionRepository.findByIdAndVideoId(10L, VIDEO_ID))
                    .willReturn(Optional.of(rendition));

            service.deleteRendition(VIDEO_ID, 10L);

            then(renditionRepository).should().delete(rendition);
        }

        @Test
        @DisplayName("should throw NotFoundException when rendition not found")
        void shouldThrowWhenNotFound() {
            given(renditionRepository.findByIdAndVideoId(99L, VIDEO_ID))
                    .willReturn(Optional.empty());

            assertThatThrownBy(() -> service.deleteRendition(VIDEO_ID, 99L))
                    .isInstanceOf(NotFoundException.class);
        }
    }

    // ----------------------------------------------------------------
    // Helpers
    // ----------------------------------------------------------------

    private VideoProcessRequest buildProcessRequest() {
        return new VideoProcessRequest(
                ProcessingMode.VERTICAL, Platform.TIKTOK, Quality.NORMAL,
                BackgroundMode.SMART_CROP, null, null, null
        );
    }

//    private VideoSummaryResponse buildVideoSummary() {
//        return new VideoSummaryResponse(VIDEO_ID, "My Video", null, null, "https://cloudinary.com/video.mp4", null, null);
//    }

    private ProcessingJob buildJob() {
        ProcessingJob job = new ProcessingJob();
        job.setJobId(JOB_ID);
        job.setVideoId(VIDEO_ID);
        job.setStatus(JobStatus.PENDING);
        return job;
    }

    private VideoJobStatusResponse buildStatusResponse() {
        return new VideoJobStatusResponse(
                JOB_ID, "processing", 45, "encoding",
                null, null, null, null, null, null, null, null, null, null
        );
    }
}
