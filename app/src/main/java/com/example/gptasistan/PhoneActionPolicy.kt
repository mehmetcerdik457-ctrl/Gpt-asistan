package com.example.gptasistan

enum class PhoneActionType {
    BACK, HOME, RECENTS, TAP, CLICK_TEXT, SCROLL_FORWARD, SCROLL_BACKWARD
}

object PhoneActionPolicy {
    private val allowed = setOf(
        PhoneActionType.BACK,
        PhoneActionType.HOME,
        PhoneActionType.RECENTS,
        PhoneActionType.TAP,
        PhoneActionType.CLICK_TEXT,
        PhoneActionType.SCROLL_FORWARD,
        PhoneActionType.SCROLL_BACKWARD
    )

    fun isAllowed(action: PhoneActionType): Boolean = action in allowed

    fun parse(raw: String): PhoneActionType? =
        runCatching { PhoneActionType.valueOf(raw.trim().uppercase()) }.getOrNull()
}
