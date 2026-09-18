buildscript {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.5.2")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.24")

        // These constraints are deliberately on the same buildscript classpath
        // that loads AGP/Kotlin. Gradle's dependency-submission guidance requires
        // this placement for vulnerable transitive dependencies introduced by plugins.
        constraints {
            classpath("io.netty:netty-buffer:4.1.137.Final")
            classpath("io.netty:netty-codec:4.1.137.Final")
            classpath("io.netty:netty-codec-http:4.1.137.Final")
            classpath("io.netty:netty-codec-http2:4.1.137.Final")
            classpath("io.netty:netty-codec-socks:4.1.137.Final")
            classpath("io.netty:netty-common:4.1.137.Final")
            classpath("io.netty:netty-handler:4.1.137.Final")
            classpath("io.netty:netty-handler-proxy:4.1.137.Final")
            classpath("io.netty:netty-resolver:4.1.137.Final")
            classpath("io.netty:netty-transport:4.1.137.Final")
            classpath("io.netty:netty-transport-native-unix-common:4.1.137.Final")
        }
    }
}
