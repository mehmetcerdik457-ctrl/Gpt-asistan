package com.mehmetcerdik.ownerbridge;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

final class AuditChain {
    static final String GENESIS = "GENESIS";

    private AuditChain() {}

    static String buildLine(long seq, long segment, String processSessionId, int pid, int bootCount,
                            long elapsedMs, long wallMs, String action, String status,
                            String resultHash, String failure, String prevHash) {
        String payload = "seq=" + seq
                + "|segment=" + segment
                + "|process_session=" + safe(processSessionId)
                + "|pid=" + pid
                + "|boot_count=" + bootCount
                + "|elapsed_ms=" + elapsedMs
                + "|wall_ms=" + wallMs
                + "|action=" + safe(action)
                + "|status=" + safe(status)
                + "|result_hash=" + safe(resultHash)
                + "|failure=" + safe(failure)
                + "|prev_hash=" + safe(prevHash);
        return payload + "|entry_hash=" + sha256(payload);
    }

    static Verification verify(String[] lines, long expectedStartSeq, String expectedStartPrev,
                               long expectedFinalSeq, String expectedHeadHash) {
        long expectedSeq = expectedStartSeq;
        String prev = expectedStartPrev == null || expectedStartPrev.isEmpty() ? GENESIS : expectedStartPrev;
        String lastHash = prev;
        int seen = 0;
        for (String line : lines) {
            if (line == null || line.trim().isEmpty()) continue;
            int cut = line.lastIndexOf("|entry_hash=");
            if (cut <= 0) return new Verification(false, "MISSING_ENTRY_HASH", seen);
            String payload = line.substring(0, cut);
            String entryHash = line.substring(cut + "|entry_hash=".length());
            if (!sha256(payload).equalsIgnoreCase(entryHash)) return new Verification(false, "ENTRY_HASH_MISMATCH", seen);
            long seq = parseLong(payload, "seq");
            String linePrev = parse(payload, "prev_hash");
            if (seq != expectedSeq) return new Verification(false, "SEQUENCE_MISMATCH", seen);
            if (!prev.equals(linePrev)) return new Verification(false, "PREVIOUS_HASH_MISMATCH", seen);
            prev = entryHash;
            lastHash = entryHash;
            expectedSeq++;
            seen++;
        }
        if (seen == 0 && expectedFinalSeq >= expectedStartSeq) return new Verification(false, "EMPTY_RETAINED_LOG", 0);
        if (seen > 0 && expectedSeq - 1 != expectedFinalSeq) return new Verification(false, "FINAL_SEQUENCE_MISMATCH", seen);
        if (seen > 0 && expectedHeadHash != null && !expectedHeadHash.equalsIgnoreCase(lastHash))
            return new Verification(false, "HEAD_HASH_MISMATCH", seen);
        return new Verification(true, "OK", seen);
    }

    private static String parse(String payload, String key) {
        String prefix = key + "=";
        for (String part : payload.split("\\|", -1)) if (part.startsWith(prefix)) return part.substring(prefix.length());
        return "";
    }

    private static long parseLong(String payload, String key) {
        try { return Long.parseLong(parse(payload, key)); } catch (Throwable t) { return Long.MIN_VALUE; }
    }

    static String sha256(String s) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] out = md.digest((s == null ? "" : s).getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(out.length * 2);
            for (byte b : out) sb.append(String.format(Locale.ROOT, "%02x", b & 0xff));
            return sb.toString();
        } catch (Throwable t) { throw new IllegalStateException("SHA256_UNAVAILABLE", t); }
    }

    private static String safe(String s) {
        if (s == null) return "";
        return s.replace("\\", "/").replace("\n", " ").replace("\r", " ").replace("|", "/");
    }

    static final class Verification {
        final boolean ok;
        final String reason;
        final int records;
        Verification(boolean ok, String reason, int records) { this.ok = ok; this.reason = reason; this.records = records; }
    }
}
