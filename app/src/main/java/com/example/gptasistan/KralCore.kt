package com.example.gptasistan

// Compatible with the command names of the original kral/safe/assistant.py.
// Parse/decide only: never grants authority to a phone tool.
sealed class KralCommand {
    data class Save(val value: String) : KralCommand()
    object ListMemory : KralCommand()
    data class AddTask(val value: String) : KralCommand()
    object ListTasks : KralCommand()
    data class FinishTask(val id: Long) : KralCommand()
    data class Speak(val value: String) : KralCommand()
    object Help : KralCommand()
    data class Chat(val value: String) : KralCommand()
    object Invalid : KralCommand()
}

object KralCore {
    fun parse(input: String): KralCommand {
        val value = input.trim()
        if (value.isEmpty()) return KralCommand.Invalid
        fun arg(prefix: String) = value.removePrefix(prefix).trim()
        return when {
            value == "/liste" -> KralCommand.ListMemory
            value == "/gorevler" -> KralCommand.ListTasks
            value == "/yardim" || value == "/help" -> KralCommand.Help
            value.startsWith("/kaydet ") -> arg("/kaydet ").let {
                if (it.isEmpty()) KralCommand.Invalid else KralCommand.Save(it)
            }
            value.startsWith("/gorev ") -> arg("/gorev ").let {
                if (it.isEmpty()) KralCommand.Invalid else KralCommand.AddTask(it)
            }
            value.startsWith("/tamam ") -> arg("/tamam ").toLongOrNull()?.let {
                if (it > 0L) KralCommand.FinishTask(it) else KralCommand.Invalid
            } ?: KralCommand.Invalid
            value.startsWith("/soyle ") -> arg("/soyle ").let {
                if (it.isEmpty()) KralCommand.Invalid else KralCommand.Speak(it)
            }
            value.startsWith("/") -> KralCommand.Invalid
            else -> KralCommand.Chat(value)
        }
    }

    fun help() = "/kaydet not · /liste · /gorev iş · /gorevler · /tamam 1 · /soyle metin · /yardim"

    // No privileged action may be delegated from this UI. A verified owner
    // identity, scoped human approval and a separate policy gate are required.
    fun privilegedExecutionAllowed() = false
}
