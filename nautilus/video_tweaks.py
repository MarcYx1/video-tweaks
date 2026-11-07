import os
import subprocess
from gi.repository import Nautilus, GObject

APP = os.path.expanduser("~/.local/bin/video-tweaks")


class VideoTweaks(GObject.GObject, Nautilus.MenuProvider):
    def _run(self, menu, paths):
        subprocess.Popen([APP, *paths])

    def get_file_items(self, files):
        paths = [f.get_location().get_path() for f in files]
        if not files or not all(p and f.get_mime_type().startswith("video/") for f, p in zip(files, paths)):
            return []
        item = Nautilus.MenuItem(name="VideoTweaks::Files", label="Video Tweaks")
        item.connect("activate", self._run, paths)
        return [item]
