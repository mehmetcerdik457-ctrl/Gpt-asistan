package com.mehmetcerdik.ownerai;

import org.junit.Test;
import static org.junit.Assert.*;

public final class VideoPipelineTest {
    @Test public void boundedVideoPolicyAcceptsNormalInput() {
        VideoPipeline.validateLimits(8L * 1024L * 1024L, 30_000L);
    }

    @Test(expected = IllegalArgumentException.class)
    public void hugeVideoIsDenied() {
        VideoPipeline.validateLimits(VideoPipeline.MAX_VIDEO_BYTES + 1L, 30_000L);
    }

    @Test(expected = IllegalArgumentException.class)
    public void excessiveDurationIsDenied() {
        VideoPipeline.validateLimits(1024L, VideoPipeline.MAX_DURATION_MS + 1L);
    }

    @Test(expected = IllegalArgumentException.class)
    public void malformedUnknownSizeIsDenied() {
        VideoPipeline.validateLimits(-1L, 1_000L);
    }
}
