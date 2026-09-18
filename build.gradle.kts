buildscript {
    repositories {
        google()
        mavenCentral()
    }

    configurations.configureEach {
        resolutionStrategy {
            force(
                "io.netty:netty-buffer:4.1.138.Final",
                "io.netty:netty-codec:4.1.138.Final",
                "io.netty:netty-codec-http:4.1.138.Final",
                "io.netty:netty-codec-http2:4.1.138.Final",
                "io.netty:netty-codec-socks:4.1.138.Final",
                "io.netty:netty-common:4.1.138.Final",
                "io.netty:netty-handler:4.1.138.Final",
                "io.netty:netty-handler-proxy:4.1.138.Final",
                "io.netty:netty-resolver:4.1.138.Final",
                "io.netty:netty-transport:4.1.138.Final",
                "io.netty:netty-transport-native-unix-common:4.1.138.Final"
            )
        }
    }
}

plugins { id("com.android.application") version "8.5.2" apply false; kotlin("android") version "1.9.24" apply false }
