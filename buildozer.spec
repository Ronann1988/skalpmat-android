[app]

# (str) Title of your application
title = SKALPMAT V7

# (str) Package name
package.name = skalpmat

# (str) Package domain (needed for android/ios packaging)
package.domain = org.nousresearch

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,db,env,log

# (str) Application versioning
version = 7.0.0

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy==2.3.0,kivymd==1.2.0,requests,python-dateutil,pytz,telebot,pytelegrambotapi,gate-api,python-dotenv

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/data/icon.png

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK,VIBRATE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_EXCHANGE

# (int) Target Android API
android.api = 33
android.minapi = 24
android.sdk = 33
android.ndk = 28c

# (bool) If True, then skip trying to update the Android sdk
android.skip_update = False

# (bool) If True, then automatically accept SDK license agreements
android.accept_sdk_license = True

# (str) Android entry point
android.entrypoint = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements Android Activity
#android.activity_class_name = org.kivy.android.PythonActivity

# (bool) enables/android auto backup of the application
android.allow_backup = True

# (str) XML that will be used to configure the backup agent
#android.backup_rules = %(source.dir)s/backup_rules.xml

# (str) The format used to package the app for release mode (aab or apk)
android.app_bundle = False

# (str) Configurations for the app bundle (only used when android.app_bundle is True)
#android.bundle.openjdk_version = 11

# (list) List of Java .jar files to add to the libs so that pyjnius can access their classes
android.add_jars = 

# (list) List of Java files to add to the android project
android.add_src = 

# (list) Android AAR archives to add
android.add_aars = 

# (list) Put these setup.py and/or pip requirements in the android project
android.add_scripts = 

# (bool) If True, then the app will be built with Gradle
android.gradle_build = True

# (int) The version of Android Gradle plugin to use
android.gradle_version = 7.4.2

# (list) Gradle dependencies to add
android.gradle_dependencies = 

# (bool) enable AndroidX support
android.enable_androidx = True

# (list) add these constraints in the project
android.p4a_dep_with_constraint = 

# (bool) skips the Gradle Daemon during build
android.gradle_daemon = True

# (str) The directory in which the android project will be created
android.project_dir = %(source.dir)s/.buildozer/android/platform/build-arm64-v8a/dists/skalpmat

# (int) The port on which the app will be deployed
#deploy.port = 

# (str) The URL of the app
#deploy.url = 

# (str) The path to the keystore file
#android.keystore_path = 

# (str) The alias of the key in the keystore
#android.keyalias = 

# (str) The password of the keystore
#android.keypass = 

# (str) The password of the keystore store
#android.storepass = 

# (list) Launch different applications on the Android device
#android.launch_activities = 

# (bool) Package the app in debug mode
android.debug = False

# (str) The log level
#log_level = 

# (bool) Enable profiling
#enable_profiling = 

# (int) The timeout in seconds for adb commands
#adb_timeout = 


#    -----------------------------------------------------------------------------
#    iOS specific parameters
#    -----------------------------------------------------------------------------

# (str) Name of the certificate to use for signing the debug version
#ios.codesign.debug = 

# (str) Name of the certificate to use for signing the release version
#ios.codesign.release = 


#    -----------------------------------------------------------------------------
#    User interface specific parameters
#    -----------------------------------------------------------------------------

# (str) Path to a custom kv file
#custom_kv_path = 


#    -----------------------------------------------------------------------------
#    Buildozer TOML specific parameters
#    -----------------------------------------------------------------------------

# (str) The name of the buildozer toml file
#buildozer_toml_filename = 


[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 0

# (str) Path to build artifact storage, absolute or relative to spec file
build_dir = ./.buildozer

# (str) Path to build output (i.e. .apk, .aab, .ipa) storage
bin_dir = ./bin