package com.example.gptasistan

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * E-posta ile 6 haneli tek kullanımlık kod (OTP) doğrulaması.
 * Kod üretimi, e-posta gönderimi, süre ve deneme sınırı sunucudadır; uygulama
 * yalnız istek başlatır ve kullanıcının girdiği kodu sunucuya doğrulatır.
 * SMTP/API anahtarı uygulamaya gömülmez.
 */
object EmailOtp {
    // No owner email is embedded in a public APK; the user enters it on the device.
    const val DEFAULT_EMAIL = ""
    const val REQUEST_PATH = "/api/v1/owner/email-otp/request"
    const val VERIFY_PATH = "/api/v1/owner/email-otp/verify"
    private val EMAIL = Regex("[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(\\.[A-Za-z0-9-]{1,63}){1,5}")
    private val CODE = Regex("[0-9]{6}")
    private val CHALLENGE = Regex("[A-Za-z0-9_-]{16,128}")

    fun validEmail(value: String) = value.length <= 254 && EMAIL.matches(value)
    fun validCode(value: String) = CODE.matches(value)

    class OtpException(message: String) : Exception(message)

    fun requestBody(email: String): JSONObject {
        require(validEmail(email))
        return JSONObject().put("email", email)
    }

    fun verifyBody(challengeId: String, code: String): JSONObject {
        require(CHALLENGE.matches(challengeId) && validCode(code))
        return JSONObject().put("challenge_id", challengeId).put("code", code)
    }

    internal fun parseChallenge(result: JSONObject): String {
        val id = result.optString("challenge_id", "")
        if (!CHALLENGE.matches(id)) throw OtpException("Sunucu geçerli bir doğrulama kimliği döndürmedi.")
        return id
    }

    internal fun parseVerified(result: JSONObject): Boolean = result.opt("verified") == true

    /** Returns the challenge id once the server has e-mailed the code. */
    fun request(base: String, email: String): String {
        val result = post(base, REQUEST_PATH, requestBody(email))
        return parseChallenge(result)
    }

    fun verify(base: String, challengeId: String, code: String): Boolean =
        parseVerified(post(base, VERIFY_PATH, verifyBody(challengeId, code)))

    private fun post(base: String, path: String, json: JSONObject): JSONObject {
        require(OwnerGateway.validBase(base))
        val connection = URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "POST"
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 8000
            connection.readTimeout = 20000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setRequestProperty("Accept", "application/json")
            connection.outputStream.use { it.write(json.toString().toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            if (status != 200) throw OtpException(when (status) {
                429 -> "Çok fazla deneme; biraz bekleyip tekrar dene."
                400, 401, 403 -> "Kod veya e-posta kabul edilmedi."
                else -> "Doğrulama sunucusu hata verdi ($status)."
            })
            JSONObject(ModelGateway.readJsonResponse(connection))
        } finally { connection.disconnect() }
    }
}
