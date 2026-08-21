package com.elevideo.backend.processing.internal.model;

/**
 * Límites editoriales seguros para clips verticales por plataforma.
 * Se mantienen centralizados para poder ajustarlos si las plataformas cambian.
 */
public final class PlatformShortLimits {

    private PlatformShortLimits() {}

    public static int maxDurationSeconds(Platform platform) {
        if (platform == null) {
            return 180;
        }

        return switch (platform) {
            case TIKTOK, INSTAGRAM, YOUTUBE_SHORTS -> 180;
        };
    }
}
