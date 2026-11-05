"""
Platform detection — one place that knows whether we're on a phone.

IS_ANDROID     running inside the Android APK (pyside6-android-deploy build)
PHONE_LAYOUT   use the narrow-screen layout. True on Android; can be forced
               on desktop with PROMETHEUS_PHONE_LAYOUT=1 to preview it.
"""

import os
import sys

IS_ANDROID = (
    sys.platform == "android" or                 # Python 3.13+ official Android builds
    hasattr(sys, "getandroidapilevel") or        # CPython built for Android
    "ANDROID_ARGUMENT" in os.environ or          # python-for-android
    "ANDROID_ROOT" in os.environ
)

PHONE_LAYOUT = IS_ANDROID or os.environ.get("PROMETHEUS_PHONE_LAYOUT") == "1"
