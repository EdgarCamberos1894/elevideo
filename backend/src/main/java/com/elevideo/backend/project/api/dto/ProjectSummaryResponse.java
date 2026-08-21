package com.elevideo.backend.project.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "Project.ProjectSummaryResponse",
        description = "Totales agregados que alimentan el resumen del dashboard."
)
public record ProjectSummaryResponse(
        @Schema(description = "Cantidad total de proyectos del usuario.")
        long projectCount,

        @Schema(description = "Cantidad total de videos en todos sus proyectos.")
        long videoCount,

        @Schema(description = "Cantidad total de videos procesados generados.")
        long conversionCount
) {
}
