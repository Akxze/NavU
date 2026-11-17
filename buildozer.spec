[app]
title = NavU
package.name = navu
package.domain = org.nationalu
source.dir = .
source.include_exts = py,kv,png,jpg,JPG,jpeg,webp,svg,json,md
source.exclude_dirs = .venv,__pycache__,tests,.buildozer,bin,ios,assets/source_archives
source.exclude_patterns = assets/floorplans/navu_floorplans_v3/navu/*.py
icon.filename = %(source.dir)s/assets/NAVU_LOGO.png
version = 0.1.0
requirements = python3,kivy==2.3.1,kivymd==2.0.0,asynckivy==0.6.4,asyncgui==0.6.3,filetype,Pillow,materialyoucolor==3.0.4,plyer
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION
p4a.local_recipes = recipes
p4a.branch = master
p4a.commit = 87a32be7feedc284d00acb303cad7da2d7a14a03

[buildozer]
log_level = 2
warn_on_root = 1
