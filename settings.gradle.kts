pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

buildscript {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    configurations.getByName("classpath") {
        resolutionStrategy.force(
            "commons-io:commons-io:2.14.0",
            "org.bitbucket.b_c:jose4j:0.9.6",
            "org.jdom:jdom2:2.0.6.1"
        )
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "GPTAsistan"
include(":app")
