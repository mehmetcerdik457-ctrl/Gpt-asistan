package com.mehmetcerdik.ownerai;

import android.content.ContentResolver;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.media.MediaMetadataRetriever;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.util.Base64;

import java.io.ByteArrayOutputStream;

public final class VideoPipeline {
    public static final long MAX_VIDEO_BYTES = 48L * 1024L * 1024L;
    public static final long MAX_DURATION_MS = 120_000L;
    public static final int SAMPLE_COUNT = 3;
    private static final int FRAME_WIDTH = 640;

    private VideoPipeline() {}

    public static void validateLimits(long bytes, long durationMs) {
        if (bytes < 0 || bytes > MAX_VIDEO_BYTES) throw new IllegalArgumentException("VIDEO_SIZE_DENIED");
        if (durationMs <= 0 || durationMs > MAX_DURATION_MS) throw new IllegalArgumentException("VIDEO_DURATION_DENIED");
    }

    public static OwnerAttachment sampleToImage(ContentResolver resolver, Uri uri, String fileName) throws Exception {
        long size = querySize(resolver, uri);
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try (ParcelFileDescriptor pfd = resolver.openFileDescriptor(uri, "r")) {
            if (pfd == null) throw new IllegalStateException("VIDEO_OPEN_FAILED");
            retriever.setDataSource(pfd.getFileDescriptor());
            String rawDuration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            long duration = rawDuration == null ? -1L : Long.parseLong(rawDuration);
            validateLimits(size, duration);

            Bitmap[] frames = new Bitmap[SAMPLE_COUNT];
            long[] pointsUs = new long[]{0L, Math.max(0L, duration * 500L), Math.max(0L, (duration - 1L) * 1000L)};
            int totalHeight = 0;
            for (int i = 0; i < SAMPLE_COUNT; i++) {
                Bitmap frame = retriever.getFrameAtTime(pointsUs[i], MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
                if (frame == null) throw new IllegalStateException("VIDEO_FRAME_DECODE_FAILED");
                frames[i] = scaleBounded(frame);
                if (frames[i] != frame) frame.recycle();
                totalHeight += frames[i].getHeight();
            }
            if (totalHeight <= 0 || totalHeight > 4096) throw new IllegalStateException("VIDEO_FRAME_BOUNDS_FAILED");
            Bitmap sheet = Bitmap.createBitmap(FRAME_WIDTH, totalHeight, Bitmap.Config.RGB_565);
            Canvas canvas = new Canvas(sheet);
            canvas.drawColor(Color.BLACK);
            int y = 0;
            for (Bitmap frame : frames) {
                canvas.drawBitmap(frame, 0f, (float)y, null);
                y += frame.getHeight();
                frame.recycle();
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            if (!sheet.compress(Bitmap.CompressFormat.JPEG, 82, out)) {
                sheet.recycle();
                throw new IllegalStateException("VIDEO_SAMPLE_ENCODE_FAILED");
            }
            sheet.recycle();
            byte[] encoded = out.toByteArray();
            if (encoded.length <= 0 || encoded.length > 8 * 1024 * 1024) throw new IllegalStateException("VIDEO_SAMPLE_OUTPUT_DENIED");
            return new OwnerAttachment(
                    OwnerAttachment.Kind.IMAGE,
                    "image/jpeg",
                    (fileName == null ? "video" : fileName) + ".sampled-frames.jpg",
                    Base64.encodeToString(encoded, Base64.NO_WRAP)
            );
        } finally {
            retriever.release();
        }
    }

    private static long querySize(ContentResolver resolver, Uri uri) {
        try (android.database.Cursor c = resolver.query(uri, new String[]{OpenableColumns.SIZE}, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int ix = c.getColumnIndex(OpenableColumns.SIZE);
                if (ix >= 0 && !c.isNull(ix)) return c.getLong(ix);
            }
        } catch (Exception ignored) {}
        return -1L;
    }

    private static Bitmap scaleBounded(Bitmap src) {
        if (src.getWidth() <= 0 || src.getHeight() <= 0) throw new IllegalArgumentException("VIDEO_FRAME_INVALID");
        float scale = Math.min(1f, ((float)FRAME_WIDTH) / src.getWidth());
        int width = Math.max(1, Math.round(src.getWidth() * scale));
        int height = Math.max(1, Math.round(src.getHeight() * scale));
        if (height > 1200) {
            float s2 = 1200f / height;
            width = Math.max(1, Math.round(width * s2));
            height = 1200;
        }
        Bitmap resized = Bitmap.createScaledBitmap(src, width, height, true);
        if (width == FRAME_WIDTH) return resized;
        Bitmap padded = Bitmap.createBitmap(FRAME_WIDTH, height, Bitmap.Config.RGB_565);
        Canvas canvas = new Canvas(padded);
        canvas.drawColor(Color.BLACK);
        canvas.drawBitmap(resized, (FRAME_WIDTH - width) / 2f, 0f, null);
        if (resized != src) resized.recycle();
        return padded;
    }
}
