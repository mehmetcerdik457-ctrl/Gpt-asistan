buildscript {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.5.2")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.24")

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
            classpath("org.bouncycastle:bcprov-jdk18on:1.86")
            classpath("org.bouncycastle:bcpkix-jdk18on:1.86")
            classpath("org.bouncycastle:bcutil-jdk18on:1.86")
            classpath("com.google.protobuf:protobuf-java:3.25.9")
            classpath("com.google.protobuf:protobuf-java-util:3.25.9")
            classpath("commons-io:commons-io:2.14.0")
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
            "io.netty:netty-transport-native-unix-common:4.1.138.Final",
            "org.bouncycastle:bcprov-jdk18on:1.86",
            "org.bouncycastle:bcpkix-jdk18on:1.86",
            "org.bouncycastle:bcutil-jdk18on:1.86",
            "com.google.protobuf:protobuf-java:3.25.9",
            "com.google.protobuf:protobuf-java-util:3.25.9"
        )
    }
}
