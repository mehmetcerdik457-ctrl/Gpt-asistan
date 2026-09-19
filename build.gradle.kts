buildscript {
    val kotlinToolchainVersion = System.getenv("KOTLIN_VERSION_OVERRIDE") ?: "2.4.20"

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    configurations.configureEach {
        resolutionStrategy.force(
            "commons-io:commons-io:2.14.0",
            "org.bitbucket.b_c:jose4j:0.9.6",
            "org.jdom:jdom2:2.0.6.1",
            "org.apache.commons:commons-compress:1.28.0"
        )
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.5.2") {
            exclude(group = "commons-io", module = "commons-io")
        }
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:$kotlinToolchainVersion")
        classpath("commons-io:commons-io:2.14.0")

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
            classpath("org.bitbucket.b_c:jose4j:0.9.6")
            classpath("org.jdom:jdom2:2.0.6.1")
            classpath("org.apache.commons:commons-compress:1.28.0")
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
            "com.google.protobuf:protobuf-java-util:3.25.9",
            "commons-io:commons-io:2.14.0",
            "org.bitbucket.b_c:jose4j:0.9.6"
        )
    }
}
