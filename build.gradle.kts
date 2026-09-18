buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        constraints {
            classpath("io.netty:netty-handler:4.1.137.Final") {
                because("Patches current critical/high Netty build-classpath advisories while AGP 8.5.2 remains in use")
            }
        }
    }
}

plugins { id("com.android.application") version "8.5.2" apply false; kotlin("android") version "1.9.24" apply false }
