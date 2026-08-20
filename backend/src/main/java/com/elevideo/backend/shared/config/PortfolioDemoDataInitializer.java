package com.elevideo.backend.shared.config;

import com.elevideo.backend.processing.internal.model.BackgroundMode;
import com.elevideo.backend.processing.internal.model.JobStatus;
import com.elevideo.backend.processing.internal.model.Platform;
import com.elevideo.backend.processing.internal.model.ProcessingJob;
import com.elevideo.backend.processing.internal.model.ProcessingMode;
import com.elevideo.backend.processing.internal.model.Quality;
import com.elevideo.backend.processing.internal.model.VideoRendition;
import com.elevideo.backend.processing.internal.repository.ProcessingJobRepository;
import com.elevideo.backend.processing.internal.repository.VideoRenditionRepository;
import com.elevideo.backend.project.internal.ProjectRepository;
import com.elevideo.backend.project.internal.model.Project;
import com.elevideo.backend.user.internal.UserRepository;
import com.elevideo.backend.user.internal.model.AccountStatus;
import com.elevideo.backend.user.internal.model.User;
import com.elevideo.backend.video.internal.VideoRepository;
import com.elevideo.backend.video.internal.model.Video;
import com.elevideo.backend.video.internal.model.VideoStatus;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "app.demo.enabled", havingValue = "true")
public class PortfolioDemoDataInitializer implements ApplicationRunner {

    private static final String DEMO_EMAIL = "demo@elevideo.app";
    private static final String SOURCE_VIDEO_URL =
            "https://res.cloudinary.com/demo/video/upload/samples/sea-turtle.mp4";
    private static final String VERTICAL_VIDEO_URL =
            "https://res.cloudinary.com/demo/video/upload/ar_9:16,c_fill,g_auto,h_1280,w_720/samples/sea-turtle.mp4";
    private static final String VERTICAL_THUMBNAIL_URL =
            "https://res.cloudinary.com/demo/video/upload/ar_9:16,c_fill,g_auto,h_960,w_540/so_2/samples/sea-turtle.jpg";
    private static final String DOG_VIDEO_URL =
            "https://res.cloudinary.com/demo/video/upload/dog.mp4";

    private final UserRepository userRepository;
    private final ProjectRepository projectRepository;
    private final VideoRepository videoRepository;
    private final ProcessingJobRepository processingJobRepository;
    private final VideoRenditionRepository videoRenditionRepository;
    private final PasswordEncoder passwordEncoder;
    private final JdbcTemplate jdbcTemplate;

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        ensureDemoSequences();

        User demoUser = seedUser();
        Project launchProject = seedProject(
                demoUser,
                "Lanzamiento de producto",
                "Videos preparados para TikTok, Reels y YouTube Shorts"
        );
        Project interviewProject = seedProject(
                demoUser,
                "Podcast e entrevistas",
                "Pruebas de encuadre automático para contenido conversacional"
        );

        Video completedVideo = seedVideo(
                launchProject,
                "Spot de naturaleza",
                "demo/sea-turtle-source",
                SOURCE_VIDEO_URL,
                79L,
                1920,
                1080,
                VideoStatus.COMPLETED
        );
        seedCompletedJob(completedVideo);

        Video failedVideo = seedVideo(
                interviewProject,
                "Entrevista para recorte inteligente",
                "demo/dog-interview",
                DOG_VIDEO_URL,
                14L,
                1280,
                720,
                VideoStatus.FAILED
        );
        seedFailedJob(failedVideo);

        seedVideo(
                interviewProject,
                "Clip listo para procesar",
                "demo/dog-ready",
                DOG_VIDEO_URL,
                14L,
                1280,
                720,
                VideoStatus.UPLOADED
        );
    }

    private void ensureDemoSequences() {
        ensureSequence("processing_jobs_seq", "processing_jobs");
        ensureSequence("video_rendition_seq", "video_rendition");
    }

    private void ensureSequence(String sequenceName, String tableName) {
        jdbcTemplate.execute("""
                DO $$
                DECLARE
                    start_value BIGINT;
                BEGIN
                    IF to_regclass('elevideo.%s') IS NULL THEN
                        SELECT COALESCE(MAX(id), 0) + 1
                        INTO start_value
                        FROM elevideo.%s;

                        EXECUTE format(
                            'CREATE SEQUENCE elevideo.%s START WITH %%s INCREMENT BY 50',
                            start_value
                        );
                    END IF;
                END
                $$;
                """.formatted(sequenceName, tableName, sequenceName));
    }

    private User seedUser() {
        User user = userRepository.findByEmail(DEMO_EMAIL).orElseGet(User::new);
        user.setFirstName("Alex");
        user.setLastName("Demo");
        user.setEmail(DEMO_EMAIL);
        user.setPassword(passwordEncoder.encode("Demo123!"));
        user.setEmailVerified(true);
        user.setAccountStatus(AccountStatus.ACTIVE);
        return userRepository.save(user);
    }

    private Project seedProject(User user, String name, String description) {
        Project project = projectRepository.findByUserIdAndName(user.getId(), name).orElseGet(Project::new);
        project.setName(name);
        project.setDescription(description);
        if (project.getUserId() == null) {
            project.setUserId(user.getId());
        }
        return projectRepository.save(project);
    }

    private Video seedVideo(
            Project project,
            String title,
            String publicId,
            String secureUrl,
            long duration,
            int width,
            int height,
            VideoStatus status
    ) {
        Video video = videoRepository.findByProjectIdAndPublicId(project.getId(), publicId).orElseGet(Video::new);
        video.setTitle(title);
        video.setPublicId(publicId);
        video.setSecureUrl(secureUrl);
        video.setFormat("mp4");
        video.setDurationInSeconds(duration);
        video.setSizeInBytes(9_094_354L);
        video.setWidth(width);
        video.setHeight(height);
        video.setStatus(status);
        if (video.getProjectId() == null) {
            video.setProjectId(project.getId());
        }
        return videoRepository.save(video);
    }

    private void seedCompletedJob(Video video) {
        if (processingJobRepository.findByJobId("demo-completed-sea-turtle").isPresent()) {
            return;
        }

        VideoRendition rendition = new VideoRendition();
        rendition.setOutputUrl(VERTICAL_VIDEO_URL);
        rendition.setPreviewUrl(VERTICAL_VIDEO_URL);
        rendition.setThumbnailUrl(VERTICAL_THUMBNAIL_URL);
        rendition.setQualityScore(0.94);
        rendition.setDurationSeconds(79.0);
        rendition.setVideoId(video.getId());
        rendition.setProcessingMode(ProcessingMode.VERTICAL);
        rendition.setQuality(Quality.HIGH);
        rendition.setBackgroundMode(BackgroundMode.SMART_CROP);
        rendition.setPlatform(Platform.INSTAGRAM);
        rendition = videoRenditionRepository.save(rendition);

        ProcessingJob job = baseJob(video, "demo-completed-sea-turtle");
        job.setStatus(JobStatus.COMPLETED);
        job.setProgressPercent(100);
        job.setPhase("completed");
        job.setElapsedSeconds(42.6);
        job.setMessage("Video vertical generado correctamente");
        job.setCompletedAt(LocalDateTime.now().minusMinutes(12));
        job.setVideoRendition(rendition);
        processingJobRepository.save(job);
    }

    private void seedFailedJob(Video video) {
        if (processingJobRepository.findByJobId("demo-failed-local-worker").isPresent()) {
            return;
        }

        ProcessingJob job = baseJob(video, "demo-failed-local-worker");
        job.setStatus(JobStatus.FAILED);
        job.setProgressPercent(18);
        job.setPhase("processor_connection");
        job.setElapsedSeconds(8.4);
        job.setMessage("No se pudo completar el procesamiento");
        job.setErrorMessage("El procesador no respondió dentro del tiempo esperado");
        job.setCompletedAt(LocalDateTime.now().minusMinutes(6));
        processingJobRepository.save(job);
    }

    private ProcessingJob baseJob(Video video, String jobId) {
        ProcessingJob job = new ProcessingJob();
        job.setJobId(jobId);
        job.setVideoId(video.getId());
        job.setProcessingMode(ProcessingMode.VERTICAL);
        job.setPlatform(Platform.INSTAGRAM);
        job.setQuality(Quality.HIGH);
        job.setBackgroundMode(BackgroundMode.SMART_CROP);
        job.setEtaSeconds(0);
        return job;
    }
}
