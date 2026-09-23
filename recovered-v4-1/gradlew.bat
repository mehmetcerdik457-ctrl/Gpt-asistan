@rem MEHMET OWNER V4.1 Gradle wrapper launcher
@echo off
set DIR=%~dp0
if not exist "%DIR%gradle\wrapper\gradle-wrapper.jar" (
  echo ERROR: gradle-wrapper.jar missing 1>&2
  exit /b 20
)
java -Xmx64m -Xms64m -Dorg.gradle.appname=gradlew -classpath "%DIR%gradle\wrapper\gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain %*
