import os
import unittest
import xml.dom.minidom

import tests  # noqa: F401  (sets sys.path)

SKINS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resources',
                     'skins')
XML = 'script-centerstage-main.xml'
LAYOUTS = [os.path.join(SKINS, 'Default', '1080i', XML),
           os.path.join(SKINS, 'skin.estuary', 'xml', XML),
           os.path.join(SKINS, 'skin.myth-estuary', 'xml', XML)]


def body(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    return text[text.index('\n<window>'):]


class Skins(unittest.TestCase):
    def test_layouts_parse(self):
        for path in LAYOUTS:
            xml.dom.minidom.parse(path)

    def test_myth_estuary_is_the_estuary_layout(self):
        self.assertEqual(body(LAYOUTS[2]), body(LAYOUTS[1]))

    def test_every_layout_has_the_controls_and_properties_python_uses(self):
        for path in LAYOUTS:
            text = body(path)
            for needed in ('id="100"', 'id="101"', 'id="200"', 'id="201"',
                           'Property(name)', 'Property(details)', 'Property(origin)',
                           'Window.Property(group)', 'Window.Property(level)',
                           'Window.Property(loading)', 'Window.Property(message)',
                           'Window.Property(empty)', 'Window.Property(dvr)',
                           'Skin.String(centerstage.background)'):
                self.assertIn(needed, text, f'{needed} missing from {path}')


if __name__ == '__main__':
    unittest.main()
