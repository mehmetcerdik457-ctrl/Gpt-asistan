package com.mehmetcerdik.ownerai;

import rikka.shizuku.ShizukuProvider;

public final class OwnerShizukuProvider extends ShizukuProvider {
    static {
        ShizukuProvider.disableAutomaticSuiInitialization();
    }
}
