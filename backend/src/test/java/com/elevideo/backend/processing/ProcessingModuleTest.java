package com.elevideo.backend.processing;

import com.elevideo.backend.processing.api.ProcessingService;
import com.elevideo.backend.processing.api.dto.VideoProcessRequest;
import com.elevideo.backend.processing.internal.model.BackgroundMode;
import com.elevideo.backend.processing.internal.model.Platform;
import com.elevideo.backend.processing.internal.model.ProcessingMode;
import com.elevideo.backend.processing.internal.model.Quality;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Test de integración del módulo processing.
 *
 * @ApplicationModuleTest arranca SOLO el módulo processing y sus dependencias
 * declaradas (video, shared), sin levantar el contexto completo de la aplicación.
 * Ideal para verificar que el módulo funciona de forma aislada.
 */
@ApplicationModuleTest
@DisplayName("Processing Module Integration")
class ProcessingModuleTest {

    @Autowired
    ProcessingService processingService;

    @Test
    @DisplayName("ProcessingService should be available as a Spring bean")
    void processingServiceShouldBeInjectable() {
        assertThat(processingService).isNotNull();
    }
}
