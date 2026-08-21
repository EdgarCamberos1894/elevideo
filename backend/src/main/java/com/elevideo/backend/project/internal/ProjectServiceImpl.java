package com.elevideo.backend.project.internal;

import com.elevideo.backend.project.api.ProjectService;
import com.elevideo.backend.project.api.dto.ProjectPageableRequest;
import com.elevideo.backend.project.api.dto.ProjectRequest;
import com.elevideo.backend.project.api.dto.ProjectResponse;
import com.elevideo.backend.project.api.dto.ProjectSummaryResponse;
import com.elevideo.backend.project.internal.model.Project;
import com.elevideo.backend.shared.security.CurrentUserProvider;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@RequiredArgsConstructor
class ProjectServiceImpl implements ProjectService {

    private final ProjectRepository   projectRepository;
    private final ProjectMapper       projectMapper;
    private final CurrentUserProvider currentUserProvider;

    @Override
    @Transactional
    public ProjectResponse create(ProjectRequest request) {
        UUID userId = currentUserProvider.getCurrentUserId();

        Project project = projectMapper.toEntity(request);
        project.setUserId(userId);

        return projectMapper.toResponse(projectRepository.save(project), 0L, 0L);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<ProjectResponse> getProjectsByUser(ProjectPageableRequest pageable) {
        UUID userId = currentUserProvider.getCurrentUserId();
        String search = pageable.normalizedSearch();

        Page<Project> projects = search == null
                ? projectRepository.findByUserId(userId, pageable.toPageable())
                : projectRepository.searchByUserId(userId, search, pageable.toPageable());

        return projects.map(project -> projectMapper.toResponse(
                project,
                projectRepository.countVideosByProjectId(project.getId()),
                projectRepository.countRenditionsByProjectId(project.getId())
        ));
    }

    @Override
    @Transactional(readOnly = true)
    public ProjectSummaryResponse getSummary() {
        UUID userId = currentUserProvider.getCurrentUserId();
        return new ProjectSummaryResponse(
                projectRepository.countByUserId(userId),
                projectRepository.countVideosByUserId(userId),
                projectRepository.countRenditionsByUserId(userId)
        );
    }

    @Override
    @Transactional(readOnly = true)
    public ProjectResponse getById(Long projectId) {
        UUID userId = currentUserProvider.getCurrentUserId();
        Project project = findOwnedProject(projectId, userId);
        return projectMapper.toResponse(
                project,
                projectRepository.countVideosByProjectId(projectId),
                projectRepository.countRenditionsByProjectId(projectId)
        );
    }

    @Override
    @Transactional
    public ProjectResponse update(Long projectId, ProjectRequest request) {
        UUID userId = currentUserProvider.getCurrentUserId();
        Project project = findOwnedProject(projectId, userId);

        projectMapper.updateEntity(request, project);
        Project saved = projectRepository.save(project);
        return projectMapper.toResponse(
                saved,
                projectRepository.countVideosByProjectId(projectId),
                projectRepository.countRenditionsByProjectId(projectId)
        );
    }

    @Override
    @Transactional
    public void delete(Long projectId) {
        UUID userId = currentUserProvider.getCurrentUserId();
        Project project = findOwnedProject(projectId, userId);
        projectRepository.delete(project);
    }

    @Override
    @Transactional(readOnly = true)
    public void assertProjectOwnedByUser(Long projectId, UUID userId) {
        if (!projectRepository.existsByIdAndUserId(projectId, userId)) {
            boolean exists = projectRepository.existsById(projectId);
            if (!exists) throw new ProjectNotFoundException(projectId);
            throw new ProjectForbiddenException(projectId);
        }
    }

    private Project findOwnedProject(Long projectId, UUID userId) {
        return projectRepository
                .findByIdAndUserId(projectId, userId)
                .orElseThrow(() -> {
                    boolean exists = projectRepository.existsById(projectId);
                    if (!exists) return new ProjectNotFoundException(projectId);
                    return new ProjectForbiddenException(projectId);
                });
    }
}
