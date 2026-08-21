package com.elevideo.backend.processing.internal.client;

import com.elevideo.backend.shared.exception.base.DomainException;

/**
 * Indica que el demo rechazó temporalmente una solicitud de procesamiento
 * para evitar abuso o saturación de recursos.
 */
public class ProcessingRateLimitException extends DomainException {

    public ProcessingRateLimitException(String message) {
        super(message);
    }
}
