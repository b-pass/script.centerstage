"""Draws resources/icon.png and resources/fanart.jpg: a play button in a spotlight, between stage
curtains. Also resources/sidemenu.png, the same picture as a white silhouette in the style of
Estuary's home menu icons (copied into Myth Estuary as media/icons/sidemenu/centerstage.png).

Usage: python3 tools/art.py (needs Pillow)
"""
import os
from PIL import Image, ImageDraw, ImageFilter

RESOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'resources')
S = 4                      # supersampling

BG = (0x0E, 0x11, 0x16)
BLUE = (0x2A, 0x6F, 0xDB)
BLUE_DARK = (0x1E, 0x52, 0xA8)
LIGHT = (0x5B, 0x95, 0xEE)
FLOOR = (0x3C, 0x46, 0x5A)
FLOOR_EDGE = (0x4B, 0x57, 0x6E)
WHITE = (0xFF, 0xFF, 0xFF)


def bezier(p0, p1, p2, p3, n=60):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return out


def draw(width, height, curtain_scale=1.0):
    """The picture is laid out 512 units tall, and `width` / `height` * 512 units wide."""
    k = height * S / 512
    w = 512 * width / height    # the width in units
    size = (width * S, height * S)

    def p(x, y):
        return (x * k, y * k)

    # the left curtain's inner edge, tied back at about two thirds of the way down
    edge = [(x * curtain_scale, y) for x, y in
            bezier((150, 40), (140, 170), (95, 270), (88, 320), 200) +
            bezier((88, 320), (95, 360), (120, 410), (128, 432), 200)[1:]]

    def inner_x(y):
        return min(edge, key=lambda q: abs(q[1] - y))[0]

    def side(pts, mirror):
        return [p(w - x if mirror else x, y) for x, y in pts]

    img = Image.new('RGB', size, BG)

    # stage floor
    d = ImageDraw.Draw(img)
    d.rectangle([p(0, 432), p(w, 512)], fill=FLOOR)
    d.rectangle([p(0, 432), p(w, 440)], fill=FLOOR_EDGE)

    # the spotlight: a beam from the top, brightest near its source, and a pool of light on the floor
    c = w / 2
    beam = Image.new('L', size, 0)
    ImageDraw.Draw(beam).polygon([p(c - 30, 40), p(c + 30, 40), p(c + 144, 440), p(c - 144, 440)],
                                 fill=255)
    fade = Image.linear_gradient('L').resize(size).point(lambda v: 150 - v * 70 // 255)
    beam = Image.composite(fade, Image.new('L', size, 0), beam)
    pool = Image.new('L', size, 0)
    ImageDraw.Draw(pool).ellipse([p(c - 144, 412), p(c + 144, 468)], fill=200)
    pool = pool.filter(ImageFilter.GaussianBlur(4 * k))
    light = Image.new('RGB', size, LIGHT)
    img = Image.composite(light, img, beam)
    img = Image.composite(light, img, pool)
    d = ImageDraw.Draw(img)

    # curtains, each with a couple of darker folds that gather at the tie
    for mirror in (False, True):
        d.polygon(side([(0, 40)] + edge + [(0, 432)], mirror), fill=BLUE)
        for f in (0.3, 0.65):
            line = [(f * inner_x(y), y) for y in range(40, 433, 4)]
            d.line(side(line, mirror), fill=BLUE_DARK, width=round(9 * k), joint='curve')
        band = side([(-10, 312), (inner_x(320) + 10, 328)], mirror)
        d.rounded_rectangle([min(band[0][0], band[1][0]), band[0][1],
                             max(band[0][0], band[1][0]), band[1][1]], radius=8 * k, fill=LIGHT)

    # valance across the top
    d.rectangle([p(0, 0), p(w, 40)], fill=BLUE_DARK)
    n = round(w / 64)
    for i in range(n):
        x0 = i * w / n
        d.pieslice([p(x0, 14), p(x0 + w / n, 66)], 0, 180, fill=BLUE_DARK)

    # the play button, centre stage
    cy, r = 300, 76
    d.polygon([p(c - r * 0.55, cy - r), p(c - r * 0.55, cy + r), p(c + r, cy)], fill=WHITE)

    return img.resize((width, height), Image.LANCZOS)


def sidemenu(size=256):
    """The curtains, valance and play button in white on transparent, about half the canvas wide
    and centred, like Estuary's icons/sidemenu/*.png. Laid out 512 units wide and 432 tall."""
    k = size * S * 0.53 / 512
    x0, y0 = size * S / 2 - 256 * k, size * S / 2 - 216 * k

    def p(x, y):
        return (x0 + x * k, y0 + y * k)

    edge = (bezier((150, 40), (140, 170), (80, 270), (70, 310), 200) +
            bezier((70, 310), (80, 360), (115, 410), (125, 432), 200)[1:])
    mask = Image.new('L', (size * S, size * S), 0)
    d = ImageDraw.Draw(mask)
    for mirror in (False, True):
        d.polygon([p(512 - x if mirror else x, y) for x, y in [(0, 40)] + edge + [(0, 432)]],
                  fill=255)
    # the valance, its scallops cut off from the curtains by a thin gap
    n = 5
    for i in range(n):
        d.pieslice([p(i * 512 / n - 12, 0), p((i + 1) * 512 / n + 12, 104)], 0, 180, fill=0)
    d.rectangle([p(0, 0), p(512, 46)], fill=255)
    for i in range(n):
        d.pieslice([p(i * 512 / n, 6), p((i + 1) * 512 / n, 80)], 0, 180, fill=255)
    cy, r = 270, 76
    d.polygon([p(256 - r * 0.55, cy - r), p(256 - r * 0.55, cy + r), p(256 + r, cy)], fill=255)
    img = Image.new('LA', mask.size, 255)
    img.putalpha(mask)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == '__main__':
    sidemenu().save(os.path.join(RESOURCES, 'sidemenu.png'), optimize=True)
    draw(512, 512).save(os.path.join(RESOURCES, 'icon.png'), optimize=True)
    draw(1920, 1080, curtain_scale=1.5).save(os.path.join(RESOURCES, 'fanart.jpg'),
                                              quality=90, optimize=True)
