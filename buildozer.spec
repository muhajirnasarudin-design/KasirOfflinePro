[app]
title = Kasir Offline Pro
package.name = kasirofflinepro
package.domain = id.offlinekasir
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,txt,md
version = 1.0.0
requirements = python3,kivy,plyer
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 23
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
