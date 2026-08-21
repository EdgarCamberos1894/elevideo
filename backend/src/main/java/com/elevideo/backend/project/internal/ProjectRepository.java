package com.elevideo.backend.project.internal;

import com.elevideo.backend.project.internal.model.Project;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface ProjectRepository extends JpaRepository<Project, Long> {

    Page<Project> findByUserId(UUID userId, Pageable pageable);

    @Query("""
            SELECT p FROM Project p
            WHERE p.userId = :userId
              AND (
                    LOWER(p.name) LIKE LOWER(CONCAT('%', :search, '%'))
                    OR LOWER(COALESCE(p.description, '')) LIKE LOWER(CONCAT('%', :search, '%'))
              )
            """)
    Page<Project> searchByUserId(
            @Param("userId") UUID userId,
            @Param("search") String search,
            Pageable pageable
    );

    Optional<Project> findByIdAndUserId(Long projectId, UUID userId);

    boolean existsByIdAndUserId(Long id, UUID userId);

    Optional<Project> findByUserIdAndName(UUID userId, String name);

    long countByUserId(UUID userId);

    @Query("SELECT COUNT(v) FROM Video v WHERE v.projectId = :projectId")
    long countVideosByProjectId(@Param("projectId") Long projectId);

    @Query("""
            SELECT COUNT(v) FROM Video v
            WHERE v.projectId IN (
                SELECT p.id FROM Project p WHERE p.userId = :userId
            )
            """)
    long countVideosByUserId(@Param("userId") UUID userId);

    @Query("""
            SELECT COUNT(r) FROM VideoRendition r
            WHERE r.videoId IN (
                SELECT v.id FROM Video v
                WHERE v.projectId IN (
                    SELECT p.id FROM Project p WHERE p.userId = :userId
                )
            )
            """)
    long countRenditionsByUserId(@Param("userId") UUID userId);
}
