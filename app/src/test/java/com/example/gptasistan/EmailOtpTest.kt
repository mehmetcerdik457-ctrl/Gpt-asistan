package com.example.gptasistan

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class EmailOtpTest {
    @Test fun validatesEmailAndCode() {
        assertTrue(EmailOtp.validEmail("user@example.com"))
        assertFalse(EmailOtp.validEmail("user@localhost"))
        assertFalse(EmailOtp.validEmail("a b@example.com"))
        assertTrue(EmailOtp.validCode("012345"))
        assertFalse(EmailOtp.validCode("12345"))
        assertFalse(EmailOtp.validCode("1234567"))
        assertFalse(EmailOtp.validCode("12345a"))
    }

    @Test fun buildsBodies() {
        assertEquals("user@example.com", EmailOtp.requestBody("user@example.com").getString("email"))
        val body = EmailOtp.verifyBody("abcdefghijklmnop", "123456")
        assertEquals("123456", body.getString("code"))
        try { EmailOtp.verifyBody("short", "123456"); fail() } catch (_: IllegalArgumentException) {}
        try { EmailOtp.verifyBody("abcdefghijklmnop", "abc"); fail() } catch (_: IllegalArgumentException) {}
    }

    @Test fun parsesResponses() {
        assertEquals("abcdefghijklmnop", EmailOtp.parseChallenge(JSONObject("""{"challenge_id":"abcdefghijklmnop"}""")))
        try { EmailOtp.parseChallenge(JSONObject("{}")); fail() } catch (_: EmailOtp.OtpException) {}
        assertTrue(EmailOtp.parseVerified(JSONObject("""{"verified":true}""")))
        assertFalse(EmailOtp.parseVerified(JSONObject("""{"verified":"true"}""")))
        assertFalse(EmailOtp.parseVerified(JSONObject("{}")))
    }
}
