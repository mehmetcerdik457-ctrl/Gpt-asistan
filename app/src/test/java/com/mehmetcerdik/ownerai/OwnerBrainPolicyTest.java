package com.mehmetcerdik.ownerai;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.assertEquals;

public final class OwnerBrainPolicyTest {
    @Test public void ownerPrivateMemoryIsNotImplicitlyExported() {
        assertEquals("[]", OwnerBrainPolicy.providerMemoryContext());
    }

    @Test public void screenReadIsAllowedWithoutActionIntent() {
        assertTrue(OwnerBrainPolicy.allowTool("Bu ekranda ne var?", "screen_read"));
        assertTrue(OwnerBrainPolicy.allowTool("What is on the screen?", "screen_read"));
    }

    @Test public void stateChangesRequireExplicitOwnerActionIntent() {
        assertFalse(OwnerBrainPolicy.allowTool("Bu ekranda ne olduğunu açıkla", "click_text"));
        assertFalse(OwnerBrainPolicy.allowTool("Explain how this works", "type_text"));
        assertFalse(OwnerBrainPolicy.allowTool("اشرح ما يظهر على الشاشة", "swipe"));
    }

    @Test public void explicitTurkishActionIntentAllowsStateChange() {
        assertTrue(OwnerBrainPolicy.allowTool("Chatbot uygulamasını aç", "launch_worker"));
        assertTrue(OwnerBrainPolicy.allowTool("Gönder düğmesine tıkla", "click_text"));
        assertTrue(OwnerBrainPolicy.allowTool("Mesaj alanına merhaba yaz", "type_text"));
    }

    @Test public void explicitEnglishActionIntentAllowsStateChange() {
        assertTrue(OwnerBrainPolicy.allowTool("Open the chatbot", "launch_worker"));
        assertTrue(OwnerBrainPolicy.allowTool("Click the send button", "click_text"));
        assertTrue(OwnerBrainPolicy.allowTool("Type hello", "type_text"));
    }

    @Test public void explicitArabicActionIntentAllowsStateChange() {
        assertTrue(OwnerBrainPolicy.allowTool("افتح التطبيق", "launch_worker"));
        assertTrue(OwnerBrainPolicy.allowTool("اضغط زر الإرسال", "click_text"));
        assertTrue(OwnerBrainPolicy.allowTool("اكتب مرحبا", "type_text"));
    }

    @Test public void substringsDoNotAccidentallyAuthorize() {
        assertFalse(OwnerBrainPolicy.explicitActionIntent("Bunun nasıl yapılacağını açıkla"));
        assertFalse(OwnerBrainPolicy.explicitActionIntent("The homepage explains the process"));
    }
}
