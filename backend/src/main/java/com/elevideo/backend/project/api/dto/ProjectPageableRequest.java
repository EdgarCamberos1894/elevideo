package com.elevideo.backend.project.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

@Schema(
        name = "Project.ProjectPageableRequest",
        description = "Parámetros de búsqueda, paginación y ordenamiento para listar proyectos."
)
public record ProjectPageableRequest(

        @Schema(description = "Página (0-indexed).", example = "0", defaultValue = "0")
        Integer page,

        @Schema(description = "Elementos por página.", example = "6", defaultValue = "20")
        Integer size,

        @Schema(
                description = "Campo de ordenamiento.",
                example = "updatedAt",
                defaultValue = "createdAt",
                allowableValues = {"createdAt", "updatedAt", "name"}
        )
        String sortBy,

        @Schema(
                description = "Dirección del ordenamiento.",
                example = "DESC",
                defaultValue = "DESC",
                allowableValues = {"ASC", "DESC"}
        )
        String sortDirection,

        @Schema(description = "Texto opcional para buscar por nombre o descripción.", example = "TikTok")
        String search
) {

    public Pageable toPageable() {
        int pageNumber = (page != null && page >= 0) ? page : 0;
        int pageSize   = (size != null && size > 0) ? Math.min(size, 50) : 20;

        String requestedSort = (sortBy != null && !sortBy.isBlank()) ? sortBy : "createdAt";
        String sortField = switch (requestedSort) {
            case "updatedAt", "name" -> requestedSort;
            default -> "createdAt";
        };
        Sort.Direction direction = "ASC".equalsIgnoreCase(sortDirection)
                ? Sort.Direction.ASC
                : Sort.Direction.DESC;

        return PageRequest.of(pageNumber, pageSize, Sort.by(direction, sortField));
    }

    public String normalizedSearch() {
        if (search == null) return null;
        String normalized = search.trim();
        return normalized.isEmpty() ? null : normalized;
    }
}
