package com.mehmetcerdik.ownerai;

interface IShizukuShellService {
    void destroy() = 16777114;
    String unlockBridgeAccessibility() = 1;
    String bootstrapBridge(in byte[] apkBytes) = 2;
}
