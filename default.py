# -*- coding: utf-8 -*-
"""Opens the Center Stage window.
RunScript(script.centerstage[,id=<entry id>][&group=<recording group>]): with no group, ask
for one first, unless ask=0 (all groups, e.g. from the home screen's list of Stages)."""
import os
import sys
from urllib.parse import parse_qsl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'lib'))

import xbmcgui  # noqa: E402

import window  # noqa: E402

OPEN_FLAG = 'script.centerstage.open'

if __name__ == '__main__':
    home = xbmcgui.Window(10000)
    if not home.getProperty(OPEN_FLAG):  # a second RunScript while the window is up does nothing
        home.setProperty(OPEN_FLAG, 'true')
        try:
            args = dict(parse_qsl('&'.join(a.lstrip('?') for a in sys.argv[1:]),
                                  keep_blank_values=True))
            window.show(args.get('id') or None, args.get('group'), args.get('ask') != '0')
        finally:
            home.clearProperty(OPEN_FLAG)
