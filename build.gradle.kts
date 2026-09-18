buildscript {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }

    configurations.classpath {
        resolutionStrategy.eachDependency {
            if (requested.group == "io.netty") {
                useVersion("4.1.137.Final")
                because("Patch Netty build-classpath advisories, including CVE-2026-75595, without shipping Netty in the app")
            }
        }
    }

    dependencies {
        classpath("com.android.tools.build:gradle:8.5.2")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.24")
    }
}
