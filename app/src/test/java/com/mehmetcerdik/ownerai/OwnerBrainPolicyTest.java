package com.mehmetcerdik.ownerai;

import org.json.JSONObject;
import org.junit.Test;

import static org.junit.Assert.*;

public final class OwnerBrainPolicyTest {
    private static OwnerBrainPolicy.Decision d(String request, String tool, JSONObject args, String pkg, boolean fresh) {
        return OwnerBrainPolicy.authorize(request, tool, args, pkg, fresh);
    }

    @Test public void readOnlyObservationDoesNotCreateAuthorization() throws Exception {
        assertTrue(d("CİHAT ekranını oku", "READ_SCREEN", new JSONObject(), OwnerBrainPolicy.WORKER_PACKAGE, false).allowed);
        assertFalse(d("CİHAT ekranını oku", "CLICK_ELEMENT",
                new JSONObject().put("target", "Gönder"), OwnerBrainPolicy.WORKER_PACKAGE, false).allowed);
    }

    @Test public void launchIsPinnedToWorkerPackage() throws Exception {
        assertTrue(d("CİHAT uygulamasını aç", "OPEN_APP",
                new JSONObject().put("package", OwnerBrainPolicy.WORKER_PACKAGE), "", false).allowed);
        assertFalse(d("CİHAT uygulamasını aç", "OPEN_APP",
                new JSONObject().put("package", "com.example.other"), "", false).allowed);
    }

    @Test public void toolArgumentsMustMatchCurrentOwnerIntent() throws Exception {
        assertTrue(d("CİHAT'ta Gönder düğmesine tıkla", "CLICK_ELEMENT",
                new JSONObject().put("target", "Gönder"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d("CİHAT'ta Gönder düğmesine tıkla", "CLICK_ELEMENT",
                new JSONObject().put("target", "Hesabı sil"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);

        assertTrue(d("CİHAT'a merhaba yaz", "TYPE_TEXT",
                new JSONObject().put("text", "merhaba"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d("CİHAT'a merhaba yaz", "TYPE_TEXT",
                new JSONObject().put("text", "başka metin"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
    }


    @Test public void scrollAndSwipeArgumentsMustMatchOwnerDirection() throws Exception {
        assertTrue(d("CİHAT'ta aşağı kaydır", "SCROLL",
                new JSONObject().put("direction", "forward"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d("CİHAT'ta aşağı kaydır", "SCROLL",
                new JSONObject().put("direction", "backward"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertTrue(d("CİHAT'ta yukarı kaydır", "SCROLL",
                new JSONObject().put("direction", "backward"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d("CİHAT'ta kaydır", "SCROLL",
                new JSONObject().put("direction", "forward"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);

        assertTrue(d("CİHAT'ta aşağı kaydır", "SWIPE",
                new JSONObject().put("direction", "forward"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d("CİHAT'ta aşağı kaydır", "SWIPE",
                new JSONObject().put("direction", "forward").put("sx", 0.1).put("sy", 0.1)
                        .put("ex", 0.9).put("ey", 0.9),
                OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
    }

    @Test public void crossPackageStateChangeFailsClosed() throws Exception {
        assertFalse(d("Gönder düğmesine tıkla", "CLICK_ELEMENT",
                new JSONObject().put("target", "Gönder"), "com.android.settings", true).allowed);
    }

    @Test public void promptInjectionCannotBecomeOwnerAuthorization() throws Exception {
        String owner = "CİHAT ekranını oku ve özetle";
        assertFalse(d(owner, "CLICK_ELEMENT",
                new JSONObject().put("target", "Gönder"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d(owner, "TYPE_TEXT",
                new JSONObject().put("text", "ekrandaki talimatı uygula"), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
    }

    @Test public void highRiskRequiresFreshOwnerAuthentication() throws Exception {
        JSONObject args = new JSONObject().put("target", "Hesabı sil");
        assertFalse(d("CİHAT'ta Hesabı sil düğmesine tıkla", "CLICK_ELEMENT",
                args, OwnerBrainPolicy.WORKER_PACKAGE, false).allowed);
        assertTrue(OwnerBrainPolicy.isHighRisk("Hesabı sil"));
    }


    @Test public void crossPackageReadAlsoFailsClosed() throws Exception {
        assertFalse(d("Ekranı oku", "READ_SCREEN",
                new JSONObject(), "com.android.settings", true).allowed);
        assertFalse(d("Gönder düğmesini bul", "FIND_ELEMENT",
                new JSONObject().put("target", "Gönder"), "com.android.settings", true).allowed);
    }

    @Test public void globalSystemActionsFailClosedWithoutDeterministicPostcondition() throws Exception {
        assertFalse(d("ana ekrana dön", "HOME", new JSONObject(), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d("son uygulamaları aç", "RECENTS", new JSONObject(), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
        assertFalse(d("bildirimleri aç", "NOTIFICATION_ACTION", new JSONObject(), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
    }

    @Test public void unknownToolFailsClosed() throws Exception {
        assertFalse(d("Bunu yap", "EXPORT_CREDENTIALS", new JSONObject(), OwnerBrainPolicy.WORKER_PACKAGE, true).allowed);
    }

    @Test public void substringsDoNotAuthorizeActions() throws Exception {
        assertFalse(OwnerBrainPolicy.explicitActionIntent("The homepage explains the process"));
        assertFalse(OwnerBrainPolicy.explicitActionIntent("Bunun nasıl yapılacağını açıkla"));
    }
}
