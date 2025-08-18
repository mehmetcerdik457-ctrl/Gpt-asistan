package com.example.gptasistan

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.snackbar.Snackbar
import android.widget.TextView

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val v = TextView(this).apply {
            text = "Merhaba Kral Mehmet! GPT Asistan açıldı."
            textSize = 20f
            setPadding(40,120,40,40)
        }
        setContentView(v)
        v.post { Snackbar.make(v, "Hazırız 👑", Snackbar.LENGTH_LONG).show() }
    }
}
