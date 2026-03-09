package com.elevideo.backend.video.internal;

import com.elevideo.backend.project.api.ProjectService;
import com.elevideo.backend.shared.event.DomainEventPublisher;
import com.elevideo.backend.shared.exception.base.NotFoundException;
import com.elevideo.backend.shared.security.CurrentUserProvider;
import com.elevideo.backend.video.api.dto.CreateVideoRequest;
import com.elevideo.backend.video.api.dto.VideoResponse;
import com.elevideo.backend.video.internal.model.Video;
import com.elevideo.backend.video.internal.storage.CloudinaryUploadResponse;
import com.elevideo.backend.video.internal.storage.VideoStoragePort;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.BDDMockito.*;

@ExtendWith(MockitoExtension.class)
@DisplayName("VideoServiceImpl")
class VideoServiceImplTest {

    @Mock VideoRepository     videoRepository;
    @Mock VideoMapper         videoMapper;
    @Mock VideoStoragePort    storagePort;
    @Mock ProjectService      projectService;
    @Mock CurrentUserProvider currentUserProvider;
    @Mock DomainEventPublisher eventPublisher;

    @InjectMocks VideoServiceImpl service;

    private static final UUID USER_ID    = UUID.randomUUID();
    private static final Long PROJECT_ID = 1L;
    private static final Long VIDEO_ID   = 10L;

    // ----------------------------------------------------------------
    // createVideo
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("createVideo()")
    class CreateVideo {

        @Test
        @DisplayName("should upload to Cloudinary, persist, and publish event")
        void shouldCreateAndPublish() {
            MockMultipartFile file = new MockMultipartFile("video", "test.mp4", "video/mp4", new byte[]{1});
            CreateVideoRequest request = new CreateVideoRequest("My Video", file);

            CloudinaryUploadResponse uploadRes = new CloudinaryUploadResponse(
                    "public-id-123", "https://cdn.cloudinary.com/video.mp4", 100L
            );
            Video video = buildVideo();
            VideoResponse videoResponse = mock(VideoResponse.class);

            given(currentUserProvider.getCurrentUserId()).willReturn(USER_ID);
            given(storagePort.upload(file)).willReturn(uploadRes);
            given(videoMapper.toVideo("My Video", uploadRes)).willReturn(video);
            given(videoMapper.toVideoResponse(video)).willReturn(videoResponse);

            VideoResponse result = service.createVideo(PROJECT_ID, request);

            then(projectService).should().assertProjectOwnedByUser(PROJECT_ID, USER_ID);
            then(videoRepository).should().save(video);
            then(eventPublisher).should().publish(any());
            assertThat(result).isNotNull();
        }

        @Test
        @DisplayName("should delete uploaded file from Cloudinary if persistence fails")
        void shouldRollbackCloudinaryOnPersistenceFailure() {
            MockMultipartFile file = new MockMultipartFile("video", "test.mp4", "video/mp4", new byte[]{1});
            CreateVideoRequest request = new CreateVideoRequest("My Video", file);

            CloudinaryUploadResponse uploadRes = new CloudinaryUploadResponse(
                    "public-id-123", "https://cdn.cloudinary.com/video.mp4", 100L
            );
            Video video = buildVideo();

            given(currentUserProvider.getCurrentUserId()).willReturn(USER_ID);
            given(storagePort.upload(file)).willReturn(uploadRes);
            given(videoMapper.toVideo(any(), any())).willReturn(video);
            given(videoRepository.save(any())).willThrow(new RuntimeException("DB error"));

            assertThatThrownBy(() -> service.createVideo(PROJECT_ID, request))
                    .isInstanceOf(RuntimeException.class);

            then(storagePort).should().delete("public-id-123");
        }
    }

    // ----------------------------------------------------------------
    // deleteVideo
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("deleteVideo()")
    class DeleteVideo {

        @Test
        @DisplayName("should delete from storage and repository")
        void shouldDeleteFromBoth() {
            Video video = buildVideo();
            given(currentUserProvider.getCurrentUserId()).willReturn(USER_ID);
            given(videoRepository.findById(VIDEO_ID)).willReturn(Optional.of(video));

            service.deleteVideo(VIDEO_ID);

            then(storagePort).should().delete("public-id-123");
            then(videoRepository).should().delete(video);
        }

        @Test
        @DisplayName("should throw NotFoundException when video does not exist")
        void shouldThrowWhenNotFound() {
            given(currentUserProvider.getCurrentUserId()).willReturn(USER_ID);
            given(videoRepository.findById(999L)).willReturn(Optional.empty());

            assertThatThrownBy(() -> service.deleteVideo(999L))
                    .isInstanceOf(NotFoundException.class);
        }
    }

    // ----------------------------------------------------------------
    // Helpers
    // ----------------------------------------------------------------

    private Video buildVideo() {
        Video v = new Video();
        v.setId(VIDEO_ID);
        v.setProjectId(PROJECT_ID);
        v.setTitle("My Video");
        v.setPublicId("public-id-123");
        v.setSecureUrl("https://cdn.cloudinary.com/video.mp4");
        return v;
    }
}
