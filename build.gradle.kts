buildscript {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }

    configurations.getByName("classpath") {
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

    dependencies {
        classpath("com.android.tools.build:gradle:8.5.2")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.24")
    }
}
