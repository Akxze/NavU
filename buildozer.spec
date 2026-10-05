[app]
title = NavU
package.name = navu
package.domain = org.nationaluniversity
source.dir = .
source.include_exts = py,kv,png,jpg,JPG,jpeg,webp
source.exclude_dirs = .venv,__pycache__,assets/source_archives
version = 0.1.0
requirements = python3,kivy==2.3.1,kivymd==2.0.0,asynckivy==0.6.4,asyncgui==0.6.3,materialshapes==0.3,pycairo,Pillow,materialyoucolor==3.0.4,plyer
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION
p4a.local_recipes = recipes

[buildozer]
log_level = 2
warn_on_root = 1
