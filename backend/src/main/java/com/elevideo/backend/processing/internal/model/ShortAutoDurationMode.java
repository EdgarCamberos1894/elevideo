package com.elevideo.backend.processing.internal.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

import java.util.Arrays;

public enum ShortAutoDurationMode {
    AUTO("auto"),
    APPROXIMATE("approximate"),
    EXACT("exact");

    private final String value;

    ShortAutoDurationMode(String value) { this.value = value; }

    @JsonValue
    public String getValue() { return value; }

    @JsonCreator
    public static ShortAutoDurationMode fromValue(String value) {
        return Arrays.stream(values())
                .filter(mode -> mode.value.equalsIgnoreCase(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("ShortAutoDurationMode inválido: " + value));
    }
}
