package com.mehmetcerdik.ownerai;

import org.json.JSONObject;

public final class OwnerAttachment {
    public enum Kind { IMAGE, FILE, AUDIO }

    public final Kind kind;
    public final String mimeType;
    public final String fileName;
    public final String base64;

    public OwnerAttachment(Kind kind, String mimeType, String fileName, String base64) {
        this.kind = kind;
        this.mimeType = mimeType == null ? "application/octet-stream" : mimeType;
        this.fileName = fileName == null || fileName.trim().isEmpty() ? "owner-input" : fileName;
        this.base64 = base64 == null ? "" : base64;
    }

    public JSONObject toResponsesContentItem() {
        JSONObject item = new JSONObject();
        try {
            if (kind == Kind.IMAGE) {
                item.put("type", "input_image");
                item.put("detail", "auto");
                item.put("image_url", "data:" + mimeType + ";base64," + base64);
            } else if (kind == Kind.AUDIO) {
                item.put("type", "input_audio");
                JSONObject audio = new JSONObject();
                audio.put("data", base64);
                audio.put("format", audioFormat(fileName, mimeType));
                item.put("input_audio", audio);
            } else {
                item.put("type", "input_file");
                item.put("filename", fileName);
                item.put("file_data", base64);
            }
        } catch (Exception ignored) {}
        return item;
    }

    public JSONObject metadata() {
        JSONObject o = new JSONObject();
        try {
            o.put("kind", kind.name());
            o.put("mime_type", mimeType);
            o.put("file_name", fileName);
            o.put("base64_chars", base64.length());
        } catch (Exception ignored) {}
        return o;
    }

    private static String audioFormat(String name, String mime) {
        String n = name == null ? "" : name.toLowerCase(java.util.Locale.ROOT);
        String m = mime == null ? "" : mime.toLowerCase(java.util.Locale.ROOT);
        if (n.endsWith(".wav") || m.contains("wav")) return "wav";
        return "mp3";
    }
}
