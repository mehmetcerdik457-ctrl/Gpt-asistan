package com.example.gptasistan
import org.junit.Assert.*
import org.junit.Test

class OmegaAgentsModelsMockTest {
    @Test fun twelveAgentProfilesAreRecoveredAndRoutable() {
        assertEquals(12, OmegaAgentProfiles.all.size)
        assertEquals(12, OmegaAgentProfiles.all.map { it.id }.toSet().size)
        OmegaAgentProfiles.all.forEach { p ->
            assertTrue(p.instruction.length > 50)
            val r = OmegaAgentHub.route("merhaba", "agent:" + p.id)
            assertEquals(p.title, r.displayName)
            assertTrue(r.systemPrompt.contains(p.instruction.take(40)))
            assertTrue(r.systemPrompt.contains("Model önerir"))
        }
    }
    @Test fun everyCatalogProviderReturnsAnswerFromMockServer() {
        val server = java.net.ServerSocket(0, 50, java.net.InetAddress.getByName("127.0.0.1"))
        val seen = java.util.Collections.synchronizedList(mutableListOf<String>())
        val t = Thread {
            while (!server.isClosed) {
                try {
                    val c = server.accept()
                    val ins = c.getInputStream()
                    val buf = StringBuilder(); var len = 0
                    // oku: başlıklar
                    val bytes = java.io.ByteArrayOutputStream()
                    var last4 = 0
                    while (true) { val b = ins.read(); if (b < 0) break; bytes.write(b); buf.append(b.toChar())
                        if (buf.endsWith("\r\n\r\n")) break }
                    val head = buf.toString()
                    Regex("(?i)content-length: (\\d+)").find(head)?.let { len = it.groupValues[1].toInt() }
                    var read = 0; while (read < len) { val b = ins.read(); if (b < 0) break; read++ }
                    val path = head.lineSequence().first().split(" ")[1]
                    val hdr = head.lineSequence().firstOrNull { it.startsWith("Authorization", true) || it.startsWith("x-api-key", true) || it.startsWith("x-goog-api-key", true) } ?: ""
                    seen += "$path|$hdr"
                    val body = when {
                        path.contains("generateContent") -> """{"candidates":[{"content":{"parts":[{"text":"MOCK_OK"}]}}]}"""
                        path.contains("messages") -> """{"content":[{"type":"text","text":"MOCK_OK"}]}"""
                        else -> """{"choices":[{"message":{"content":"MOCK_OK"}}]}"""
                    }
                    val resp = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${body.toByteArray().size}\r\nConnection: close\r\n\r\n$body"
                    c.getOutputStream().write(resp.toByteArray()); c.getOutputStream().flush(); c.close()
                } catch (_: Exception) { }
            }
        }
        t.isDaemon = true; t.start()
        try {
            val base = "http://127.0.0.1:" + server.localPort
            assertEquals(8, OmegaModelCatalog.providers.size)
            OmegaModelCatalog.providers.forEach { p ->
                val ep = when (p.kind) {
                    OmegaProviderKind.GEMINI -> "$base/v1beta/models"
                    OmegaProviderKind.ANTHROPIC -> "$base/v1/messages"
                    else -> "$base/v1/chat/completions"
                }
                val key = if (p.requiresSecret) "TEST_KEY_${p.id}" else null
                assertEquals("MOCK_OK", OmegaMultiModelClient.chat(p.copy(endpoint = ep), key, "selam", "sys", ep))
            }
            assertTrue(seen.any { it.contains("gemini-3.5-flash:generateContent") })
            assertTrue(seen.any { it.contains("TEST_KEY_xai") })
            assertTrue(seen.any { it.contains("TEST_KEY_anthropic") })
            assertEquals(8, seen.size)
        } finally { server.close() }
    }
}
