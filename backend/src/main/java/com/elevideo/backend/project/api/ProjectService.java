package com.elevideo.backend.project.api;

import com.elevideo.backend.project.api.dto.ProjectPageableRequest;
import com.elevideo.backend.project.api.dto.ProjectRequest;
import com.elevideo.backend.project.api.dto.ProjectResponse;
import com.elevideo.backend.project.api.dto.ProjectSummaryResponse;
import org.springframework.data.domain.Page;

import java.util.UUID;

/**
 * API pública del módulo project.
 * Solo esta interfaz puede ser usada por otros módulos.
 */
public interface ProjectService {

    /**
     * Crea un nuevo proyecto para el usuario autenticado.
     */
    ProjectResponse create(ProjectRequest request);

    /**
     * Retorna los proyectos del usuario autenticado con búsqueda, paginación y ordenamiento.
     */
    Page<ProjectResponse> getProjectsByUser(ProjectPageableRequest pageable);

    /**
     * Retorna los totales agregados necesarios para el dashboard.
     */
    ProjectSummaryResponse getSummary();

    /**
     * Retorna un proyecto por ID, validando que pertenezca al usuario autenticado.
     */
    ProjectResponse getById(Long projectId);

    /**
     * Actualiza nombre y descripción de un proyecto existente.
     */
    ProjectResponse update(Long projectId, ProjectRequest request);

    /**
     * Elimina un proyecto y sus videos en cascada.
     */
    void delete(Long projectId);

    /**
     * Verifica que un proyecto exista y pertenezca al usuario indicado.
     * Usado internamente por el módulo video.
     *
     * @throws com.elevideo.backend.project.internal.ProjectNotFoundException si no existe
     * @throws com.elevideo.backend.project.internal.ProjectForbiddenException si no pertenece al usuario
     */
    void assertProjectOwnedByUser(Long projectId, UUID userId);
}
