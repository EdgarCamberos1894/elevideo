package com.elevideo.backend.processing.internal.client;

import com.elevideo.backend.shared.security.JwtService;
import com.elevideo.backend.shared.security.TokenPurpose;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import java.util.UUID;

/**
 * Cliente HTTP hacia el microservicio Python de procesamiento.
 * Gestiona autenticación (JWT + API Key) y manejo de errores centralizado.
 */
@Slf4j
@Component
public class PythonServiceClient {

    private static final int POST_MAX_ATTEMPTS = 2;
    private static final long POST_RETRY_DELAY_MS = 350L;

    private final JwtService jwtService;
    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    @org.springframework.beans.factory.annotation.Value("${python.service.url}")
    private String pythonServiceUrl;

    @org.springframework.beans.factory.annotation.Value("${python.service.api-key}")
    private String serviceApiKey;

    public PythonServiceClient(JwtService jwtService, ObjectMapper objectMapper) {
        this.jwtService = jwtService;
        this.objectMapper = objectMapper;
        this.restClient = RestClient.builder()
                .requestFactory(new SimpleClientHttpRequestFactory())
                .build();
    }

    public <T> T post(String path, Object body, Class<T> responseType, UUID userId) {
        String idempotencyKey = UUID.randomUUID().toString();
        log.debug(
                "POST Python service | path={} | userId={} | idempotencyKey={}",
                path, userId, idempotencyKey
        );

        for (int attempt = 1; attempt <= POST_MAX_ATTEMPTS; attempt++) {
            try {
                return restClient.post()
                        .uri(pythonServiceUrl + path)
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-Service-Key", serviceApiKey)
                        .header("Authorization", "Bearer " + serviceToken(userId))
                        .header("Idempotency-Key", idempotencyKey)
                        .body(body)
                        .retrieve()
                        .body(responseType);
            } catch (HttpClientErrorException e) {
                return handleClient(e, path);
            } catch (HttpServerErrorException e) {
                if (attempt < POST_MAX_ATTEMPTS && isTransientServerError(e)) {
                    log.warn(
                            "Fallo transitorio del procesador | path={} | status={} | intento={}/{}; reintentando",
                            path, e.getStatusCode(), attempt, POST_MAX_ATTEMPTS
                    );
                    pauseBeforeRetry(path);
                    continue;
                }
                return handleServer(e, path);
            } catch (ResourceAccessException e) {
                if (attempt < POST_MAX_ATTEMPTS) {
                    log.warn(
                            "Conexión transitoria al procesador | path={} | intento={}/{} | error={}; reintentando",
                            path, attempt, POST_MAX_ATTEMPTS, e.getMessage()
                    );
                    pauseBeforeRetry(path);
                    continue;
                }
                throw unavailable(path, e);
            }
        }

        throw new PythonServiceException("No se pudo iniciar el procesamiento.");
    }

    public <T> T get(String path, Class<T> responseType, UUID userId) {
        log.debug("GET Python service | path={} | userId={}", path, userId);
        try {
            return restClient.get()
                    .uri(pythonServiceUrl + path)
                    .header("X-Service-Key", serviceApiKey)
                    .header("Authorization", "Bearer " + serviceToken(userId))
                    .retrieve()
                    .body(responseType);
        } catch (HttpClientErrorException e)  { return handleClient(e, path); }
        catch (HttpServerErrorException e)    { return handleServer(e, path); }
        catch (ResourceAccessException e)     { throw unavailable(path, e);   }
    }

    public <T> T postEmpty(String path, Class<T> responseType, UUID userId) {
        log.debug("POST (sin body) Python service | path={} | userId={}", path, userId);
        try {
            return restClient.post()
                    .uri(pythonServiceUrl + path)
                    .header("X-Service-Key", serviceApiKey)
                    .header("Authorization", "Bearer " + serviceToken(userId))
                    .retrieve()
                    .body(responseType);
        } catch (HttpClientErrorException e)  { return handleClient(e, path); }
        catch (HttpServerErrorException e)    { return handleServer(e, path); }
        catch (ResourceAccessException e)     { throw unavailable(path, e);   }
    }

    private String serviceToken(UUID userId) {
        return jwtService.generateServiceToken(userId);
    }

    private boolean isTransientServerError(HttpServerErrorException e) {
        int status = e.getStatusCode().value();
        return status == 502 || status == 503 || status == 504;
    }

    private void pauseBeforeRetry(String path) {
        try {
            Thread.sleep(POST_RETRY_DELAY_MS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("Reintento interrumpido | path={}", path);
            throw new PythonServiceException("El intento de procesamiento fue interrumpido.");
        }
    }

    private <T> T handleClient(HttpClientErrorException e, String path) {
        log.warn("Error cliente Python | path={} | status={}", path, e.getStatusCode());
        if (e.getStatusCode() == HttpStatus.NOT_FOUND)
            throw new PythonServiceException("El recurso solicitado no existe.");
        if (e.getStatusCode() == HttpStatus.UNAUTHORIZED || e.getStatusCode() == HttpStatus.FORBIDDEN)
            throw new PythonServiceException("Error de configuración interna. Contacta al administrador.");
        if (e.getStatusCode() == HttpStatus.TOO_MANY_REQUESTS)
            throw new ProcessingRateLimitException(
                    extractDetail(e, "Hay demasiados procesamientos pendientes. Intenta nuevamente más tarde.")
            );
        if (e.getStatusCode() == HttpStatus.BAD_REQUEST)
            throw new PythonServiceException("Solicitud inválida: " + extractDetail(e, e.getResponseBodyAsString()));
        if (e.getStatusCode() == HttpStatus.CONFLICT)
            throw new PythonServiceException("La solicitud de procesamiento entró en conflicto con un intento previo.");
        throw new PythonServiceException("Error al comunicarse con el servicio de procesamiento.");
    }

    private <T> T handleServer(HttpServerErrorException e, String path) {
        log.error("Error servidor Python | path={} | status={}", path, e.getStatusCode());
        if (e.getStatusCode() == HttpStatus.SERVICE_UNAVAILABLE) {
            throw new PythonServiceException(
                    extractDetail(e, "El procesador está ocupado. Intenta nuevamente en un momento.")
            );
        }
        throw new PythonServiceException("El servicio de procesamiento falló. Intenta de nuevo.");
    }

    private String extractDetail(HttpStatusCodeException e, String fallback) {
        try {
            JsonNode body = objectMapper.readTree(e.getResponseBodyAsString());
            String detail = body.path("detail").asText();
            return detail == null || detail.isBlank() ? fallback : detail;
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private PythonServiceException unavailable(String path, ResourceAccessException e) {
        log.error("No se pudo conectar al microservicio Python | path={} | error={}", path, e.getMessage());
        return new PythonServiceException("El servicio de procesamiento no está disponible. Intenta más tarde.");
    }
}
