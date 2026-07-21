import sys
import os

_ROOT = os.path.dirname(__file__)
for _subdir in (
    'src',
    'f469-disco/libs/common',
    'f469-disco/libs/unix',
    'f469-disco/usermods/udisplay_f469/display_unixport',
    'test',
):
    _path = os.path.join(_ROOT, _subdir)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from native_support import setup_native_stubs
setup_native_stubs()
