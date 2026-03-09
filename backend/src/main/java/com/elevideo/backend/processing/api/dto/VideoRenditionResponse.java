package com.elevideo.backend.processing.api.dto;

import com.elevideo.backend.processing.internal.model.BackgroundMode;
import com.elevideo.backend.processing.internal.model.Platform;
import com.elevideo.backend.processing.internal.model.ProcessingMode;

import java.time.LocalDateTime;

public record VideoRenditionResponse(
        Long           id,
        String         outputUrl,
        String         thumbnailUrl,
        String         previewUrl,
        ProcessingMode processingMode,
        Platform       platform,
        BackgroundMode backgroundMode,
        LocalDateTime  createdAt
) {}
