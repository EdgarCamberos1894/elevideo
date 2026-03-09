package com.elevideo.backend;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

/**
 * Verifica que la estructura modular del proyecto sea válida:
 * - Ningún módulo importa paquetes 'internal' de otro módulo.
 * - Las dependencias entre módulos respetan el grafo definido.
 *
 * Este test falla en CI si alguien rompe una frontera de módulo,
 * actuando como guardia arquitectural automático.
 */
class ModularStructureTest {

    private static final ApplicationModules modules =
            ApplicationModules.of(ElevideoBackendApplication.class);

    @Test
    void applicationModulesAreCompliant() {
        modules.verify();
    }

    /**
     * Genera documentación del grafo de dependencias entre módulos
     * en /target/spring-modulith-docs/ (PlantUML + AsciiDoc).
     * Ejecutar manualmente cuando se quiera actualizar la documentación.
     */
    @Test
    void writeDocumentationSnippets() {
        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml()
                .writeModuleCanvases();
    }
}
