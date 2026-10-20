package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

class KralCoreTest {
    @Test fun pythonLegacySaveCommand() {
        assertEquals(KralCommand.Save("Deneme"), KralCore.parse("/kaydet Deneme"))
    }
    @Test fun pythonLegacyListAndSpeak() {
        assertEquals(KralCommand.ListMemory, KralCore.parse("/liste"))
        assertEquals(KralCommand.Speak("merhaba"), KralCore.parse("/soyle merhaba"))
    }
    @Test fun taskWorkflow() {
        assertEquals(KralCommand.AddTask("Test"), KralCore.parse("/gorev Test"))
        assertEquals(KralCommand.ListTasks, KralCore.parse("/gorevler"))
        assertEquals(KralCommand.FinishTask(2), KralCore.parse("/tamam 2"))
    }
    @Test fun invalidCommandsFailClosed() {
        assertEquals(KralCommand.Invalid, KralCore.parse("/tamam -1"))
        assertEquals(KralCommand.Invalid, KralCore.parse("/tamam xyz"))
        assertEquals(KralCommand.Invalid, KralCore.parse("/kaydet "))
        assertEquals(KralCommand.Invalid, KralCore.parse("/root"))
        assertFalse(KralCore.privilegedExecutionAllowed())
    }
    @Test fun unrecognizedTextIsChat() {
        assertEquals(KralCommand.Chat("Selam"), KralCore.parse("Selam"))
    }
}
