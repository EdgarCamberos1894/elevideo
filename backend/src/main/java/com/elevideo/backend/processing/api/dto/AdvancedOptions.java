package com.elevideo.backend.processing.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

@Schema(name = "VideoProcessing.AdvancedOptions",
        description = "Opciones avanzadas efectivas para seguimiento, composición y nitidez. Todos opcionales.")
public record AdvancedOptions(

        @Min(10) @Max(100)
        Integer maxCameraSpeed,

        Boolean applySharpening,
        Boolean useRuleOfThirds,

        @Min(0) @Max(50)
        Integer edgePadding
) {}
