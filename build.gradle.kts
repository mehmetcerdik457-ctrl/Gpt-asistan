buildscript {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.5.2")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.4.20")

        // Build-tool dependencies stay on one patched Netty line. The plugin
        // classpath is constrained here because this is where AGP/Kotlin load.
        constraints {
            classpath("io.netty:netty-buffer:4.1.138.Final")
            classpath("io.netty:netty-codec:4.1.138.Final")
            classpath("io.netty:netty-codec-http:4.1.138.Final")
            classpath("io.netty:netty-codec-http2:4.1.138.Final")
            classpath("io.netty:netty-codec-socks:4.1.138.Final")
            classpath("io.netty:netty-common:4.1.138.Final")
            classpath("io.netty:netty-handler:4.1.138.Final")
            classpath("io.netty:netty-handler-proxy:4.1.138.Final")
            classpath("io.netty:netty-resolver:4.1.138.Final")
            classpath("io.netty:netty-transport:4.1.138.Final")
            classpath("io.netty:netty-transport-native-unix-common:4.1.138.Final")
        }
    }
}

allprojects {
    configurations.configureEach {
        resolutionStrategy.force(
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
