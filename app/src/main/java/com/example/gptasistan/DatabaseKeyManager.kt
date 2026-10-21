package com.example.gptasistan

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.io.File
import java.io.FileInputStream
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal fun interface DatabaseKeyProvider {
    fun getKey(context: Context): ByteArray
}

/** Wraps a random SQLCipher passphrase with a non-exportable Android Keystore AES key. */
internal object AndroidDatabaseKeyProvider : DatabaseKeyProvider {
    private const val KEYSTORE = "AndroidKeyStore"
    private const val WRAPPING_KEY_ALIAS = "kral.database.wrapping.v1"
    private const val PREFS = "kral_database_key"
    private const val PREF_KEY = "wrapped_sqlcipher_key_v1"
    private const val AAD = "KRAL-SQLCIPHER-KEY-V1"
    private const val IV_BYTES = 12
    private const val KEY_BYTES = 32

    override fun getKey(context: Context): ByteArray {
        val appContext = context.applicationContext
        val prefs = appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stored = prefs.getString(PREF_KEY, null)
        if (stored != null) return unwrap(getWrappingKey(create = false), stored)

        val mainDb = appContext.getDatabasePath(KralStore.DATABASE_NAME)
        if (mainDb.exists() && !isPlaintextSqlite(mainDb)) {
            throw IllegalStateException("Şifreli veritabanı anahtarı eksik; veriler korunmak için kapalı tutuldu.")
        }

        val rawKey = ByteArray(KEY_BYTES).also(SecureRandom()::nextBytes)
        val wrapped = wrap(getWrappingKey(create = true), rawKey)
        check(prefs.edit().putString(PREF_KEY, wrapped).commit()) {
            "Şifreli veritabanı anahtarı güvenli şekilde kaydedilemedi."
        }
        return rawKey
    }

    private fun getWrappingKey(create: Boolean): SecretKey {
        val store = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        val existing = store.getKey(WRAPPING_KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing
        check(create) { "Android Keystore veritabanı anahtarı bulunamadı." }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                WRAPPING_KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setKeySize(256)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build(),
        )
        return generator.generateKey()
    }

    private fun wrap(key: SecretKey, rawKey: ByteArray): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        cipher.updateAAD(AAD.toByteArray(Charsets.UTF_8))
        val encrypted = cipher.doFinal(rawKey)
        return Base64.encodeToString(cipher.iv + encrypted, Base64.NO_WRAP)
    }

    private fun unwrap(key: SecretKey, encoded: String): ByteArray {
        val blob = Base64.decode(encoded, Base64.NO_WRAP)
        require(blob.size == IV_BYTES + KEY_BYTES + 16) { "Saklanan veritabanı anahtarı bozuk." }
        val iv = blob.copyOfRange(0, IV_BYTES)
        val encrypted = blob.copyOfRange(IV_BYTES, blob.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, iv))
        cipher.updateAAD(AAD.toByteArray(Charsets.UTF_8))
        return cipher.doFinal(encrypted).also {
            require(it.size == KEY_BYTES) { "Saklanan veritabanı anahtarı geçersiz." }
        }
    }

    private fun isPlaintextSqlite(file: File): Boolean {
        if (!file.isFile || file.length() < 16) return false
        val header = ByteArray(16)
        FileInputStream(file).use { input ->
            if (input.read(header) != header.size) return false
        }
        return header.contentEquals("SQLite format 3\u0000".toByteArray(Charsets.US_ASCII))
    }
}
