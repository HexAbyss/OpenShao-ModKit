"""Visual style of the ModKit window: palette, typeface (Hanken Grotesk, three weights), text sizes and the shapes drawn by hand (buttons,
links, switch, progress bar, background, brush circle). All measures are in logical pixels; ImGui scales them for the display.

Everything is drawn into the window's draw list through a Canvas. Hit areas are invisible buttons placed over the drawn shapes."""
import math
import os

import numpy as np
from imgui_bundle import hello_imgui, imgui, immvision

# ---- palette (0xRRGGBB) ----
INK, SLATE, LINE, MIST, DIM = 0x25282C, 0x30343A, 0x3B4047, 0x959AA0, 0x6C7278
PAPER, EMBER, MOSS, WARNING = 0xECE5D6, 0xE0705A, 0x93B79E, 0xE8A15A
EMBER_HOVER, LINK_HOVER = 0xE8826C, 0xF09A84

REGULAR, MEDIUM, SEMIBOLD = 0, 1, 2
FONT_FILES = ('HankenGrotesk-Regular.ttf', 'HankenGrotesk-Medium.ttf', 'HankenGrotesk-SemiBold.ttf')
_fonts = [None, None, None]


def rgb(value, alpha=1.0):
    """An ImGui colour (the packed ABGR integer) from 0xRRGGBB and an alpha from 0 to 1"""
    a = int(min(max(alpha, 0.0), 1.0) * 255 + 0.5)
    return ((value >> 16) & 255) | (((value >> 8) & 255) << 8) | ((value & 255) << 16) | (a << 24)


def load_fonts():
    """Called once the window exists: loads the three weights"""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
    for weight, name in enumerate(FONT_FILES):
        _fonts[weight] = hello_imgui.load_font_ttf(os.path.join(folder, name), 20.0)


def apply_style():
    """Sets the ImGui style used by the real widgets (text fields) and the scroll bars"""
    style = imgui.get_style()
    style.window_padding = (0, 0)
    style.window_border_size = 0
    style.window_rounding = 0
    style.frame_rounding = 8
    style.scrollbar_size = 8
    style.scrollbar_rounding = 4

    def color(index, value, alpha=1.0):
        c = rgb(value, alpha)
        style.set_color_(index, imgui.color_convert_u32_to_float4(c))
    clear = (0, 0, 0, 0)
    style.set_color_(imgui.Col_.window_bg, clear)
    style.set_color_(imgui.Col_.child_bg, clear)
    style.set_color_(imgui.Col_.scrollbar_bg, clear)
    color(imgui.Col_.scrollbar_grab, LINE)
    color(imgui.Col_.scrollbar_grab_hovered, DIM)
    color(imgui.Col_.scrollbar_grab_active, MIST)
    color(imgui.Col_.nav_cursor, EMBER)
    color(imgui.Col_.frame_bg, SLATE)
    color(imgui.Col_.frame_bg_hovered, SLATE)
    color(imgui.Col_.frame_bg_active, SLATE)
    color(imgui.Col_.border, LINE)
    color(imgui.Col_.text, PAPER)
    color(imgui.Col_.text_selected_bg, EMBER, 0.35)
    color(imgui.Col_.text_disabled, DIM)


class Canvas:
    """Drawing in logical pixels at an origin (the window's top left, or a child's)"""
    def __init__(self, draw_list, origin=(0.0, 0.0)):
        self.list = draw_list
        self.origin = origin

    def p(self, x, y):
        return imgui.ImVec2(self.origin[0] + x, self.origin[1] + y)

    def measure(self, weight, size, text, wrap=0.0):
        imgui.push_font(_fonts[weight], size)
        measured = imgui.calc_text_size(text, False, wrap if wrap > 0 else -1.0)
        imgui.pop_font()
        return measured.x, measured.y

    def text(self, weight, size, x, y, color, text, wrap=0.0):
        self.list.add_text(_fonts[weight], size, self.p(x, y), color, text, wrap)

    def text_centered(self, weight, size, cx, y, color, text):
        self.text(weight, size, cx - self.measure(weight, size, text)[0] / 2, y, color, text)

    def text_right(self, weight, size, right, y, color, text):
        self.text(weight, size, right - self.measure(weight, size, text)[0], y, color, text)

    def rect(self, x0, y0, x1, y1, color, rounding=0.0):
        self.list.add_rect_filled(self.p(x0, y0), self.p(x1, y1), color, rounding)

    def outline(self, x0, y0, x1, y1, color, rounding, thickness=1.2):
        self.list.add_rect(self.p(x0, y0), self.p(x1, y1), color, rounding, thickness)

    def rule(self, x0, x1, y):
        self.list.add_rect_filled(self.p(x0, y), self.p(x1, y + 1), rgb(LINE))

    def fit(self, weight, size, width, text):
        """Shortens text in the middle, as for long paths, keeping more of the end, which names the file or folder"""
        if self.measure(weight, size, text)[0] <= width:
            return text
        for keep in range(len(text), 4, -1):
            head = keep // 3
            tail = keep - head
            candidate = text[:head] + '...' + text[len(text) - tail:]
            if self.measure(weight, size, candidate)[0] <= width:
                return candidate
        return '...'

    def toggle(self, x, y, on, hovered):
        self.rect(x, y, x + 38, y + 22, rgb(EMBER if on else SLATE, 1.0 if hovered else 0.92), 11)
        if not on:
            self.outline(x, y, x + 38, y + 22, rgb(DIM if hovered else LINE), 11)
        self.list.add_circle_filled(self.p(x + 27 if on else x + 11, y + 11), 7.5, rgb(INK if on else MIST), 24)

    def progress_bar(self, x0, x1, y, value):
        self.rect(x0, y, x1, y + 3, rgb(SLATE), 2)
        if value > 0:
            self.rect(x0, y, x0 + (x1 - x0) * min(max(value, 0.0), 1.0), y + 3, rgb(EMBER), 2)

    def brush_dash(self, x, y, length):
        """The brush stroke under the active tab"""
        r = Rng(5)
        for k in range(6):
            row = y + k * 0.55
            self.list.add_line(self.p(x + r.f() * 2, row), self.p(x + length * (0.75 + 0.25 * r.f()), row + 0.4), rgb(EMBER, 0.85), 1.2)


class Rng:
    """Small linear congruential generator: a seeded drawing has the same marks on every run"""
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def f(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return (self.s >> 8) / 16777216.0


# ---- the background: ink, a soft light, paper grain; made once per size as a picture ----
_background = {}


def background_texture(width, height, light_x, light_y):
    key = (width, height, round(light_x), round(light_y))
    if key not in _background:
        _background.clear()
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        distance = np.hypot(xs + 0.5 - light_x, ys + 0.5 - light_y)
        covering = np.zeros((height, width), np.float32)
        for i in range(18, 0, -1):
            covering += distance < 430.0 * i / 18.0
        keep = np.float32(0.95) ** covering               # each of the 18 discs lets 95% through
        ink = np.array([(INK >> 16) & 255, (INK >> 8) & 255, INK & 255], np.float32)
        light = np.array([0x3A, 0x3F, 0x45], np.float32)
        image = ink + (light - ink) * (1 - keep)[..., None]
        rng = np.random.default_rng(99)
        count = int(2600 * width * height / (1040 * 640))
        px, py = rng.integers(0, width, count), rng.integers(0, height, count)
        bright = rng.random(count) < 0.5
        warm = np.array([255, 250, 240], np.float32)
        image[py[bright], px[bright]] += (warm - image[py[bright], px[bright]]) * (9 / 255)
        image[py[~bright], px[~bright]] *= 1 - 14 / 255
        rgba = np.dstack([np.clip(image, 0, 255).astype(np.uint8), np.full((height, width), 255, np.uint8)])
        _background[key] = immvision.GlTexture(rgba)
    return _background[key]


def draw_background(canvas, width, height, light_x, light_y):
    texture = background_texture(int(width), int(height), light_x, light_y)
    canvas.list.add_image(imgui.ImTextureRef(texture.texture_id), canvas.p(0, 0), canvas.p(int(width), int(height)))


def glow(canvas, cx, cy, radius, strength):
    for i in range(18, 0, -1):
        canvas.list.add_circle_filled(canvas.p(cx, cy), radius * (0.75 + 0.95 * i / 18.0), rgb(0x8A3E33, 0.024 * strength), 128)


# ---- the ensō (brush circle): rendered once into a picture and cached; progress is a mask over that picture ----
def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


_FLAME = np.array([[0xA5, 0x31, 0x3A], [0xCC, 0x48, 0x44], [0xE8, 0x70, 0x4F], [0xF7, 0xAC, 0x60]], np.float32)


def _flame(t, edge):
    m = np.clip(0.02 + 0.62 * t + 0.48 * edge * edge, 0.0, 0.999) * 3.0
    i = m.astype(np.int32)
    f = (m - i)[..., None]
    return _FLAME[i] * (1 - f) + _FLAME[i + 1] * f


def enso_base(radius, width, seed=11, bristles=44, supersample=1):
    """The whole brush circle, as (RGBA array, side, t map). Each bristle is a ribbon with its own ink amount, pressure and dryness along the stroke. The t map says,
    for each pixel, how far along the stroke (0 to 1) the ink there was laid, which is what lets a progress be drawn by hiding the part
    of the stroke that has not been reached yet, without drawing the circle again."""
    start, sweep = -112.0 * math.pi / 180.0, 336.0 * math.pi / 180.0
    steps = max(24, int(radius * 2.2))
    pad = int(radius * 0.08 + width + 6)
    size = int(2 * radius + 2 * pad)
    ss = supersample
    center = size / 2.0
    big = size * ss
    rng = Rng(seed)
    over = 4                                          # samples per step along the stroke: dense enough that consecutive discs overlap into a continuous line
    samples = []
    for k in range(bristles):
        o = 0.0 if bristles == 1 else k / (bristles - 1) - 0.5
        edge = abs(o) * 2.0
        end = 1.0 - rng.f() * (0.04 + 0.30 * edge * edge)
        begin = rng.f() * 0.02 * edge
        shade = 0.70 + 0.30 * rng.f()
        f1, f2 = 18 + rng.f() * 30, 41 + rng.f() * 60
        p1, p2 = rng.f() * 6.28, rng.f() * 6.28
        dryness = 0.25 + 0.75 * edge + (rng.f() - 0.5) * 0.3
        limit = end
        if limit <= begin:
            continue
        half = max(1.0, width / bristles * 2.2) * 0.5
        n = (int(steps * (limit - begin)) + 2) * over
        t = begin + (limit - begin) * np.arange(n + 1, dtype=np.float32) / n
        noise = 0.5 + 0.32 * np.sin(t * f1 + p1) + 0.18 * np.sin(t * f2 + p2)
        threshold = _smooth(0.50, 1.0, t) * dryness * 1.15
        ink = _smooth(threshold - 0.09, threshold + 0.09, noise)
        ink = ink * _smooth(begin, begin + 0.012, t) * (1.0 - _smooth(limit - 0.035, limit, t))
        press = (0.66 + 0.40 * np.sin(t * math.pi * 0.9 + 0.2)) * (0.80 + 0.35 * (1 - _smooth(0.0, 0.06, t))) * (1.0 - 0.70 * _smooth(0.70, 1.0, t))
        w = width * press
        rr = radius * (1.0 + 0.03 * (0.5 - t)) + radius * (0.008 * np.sin(t * 9 + seed) + 0.005 * np.sin(t * 23 + seed * 0.7)) + o * w
        angle = start + sweep * t
        a = (0.82 + 0.18 * shade) * ink
        a = 1.0 - np.power(np.clip(1.0 - a, 1e-4, 1.0), 1.0 / (over + 1))      # the extra points must not add up to more ink
        samples.append((((center + np.cos(angle) * rr) * ss).astype(np.float32), ((center + np.sin(angle) * rr) * ss).astype(np.float32),
                        a.astype(np.float32), _flame(t, np.float32(edge)), t, np.full(n + 1, half * ss, np.float32)))
    x, y, a, colour, t, solid = (np.concatenate([s[i] for s in samples]) for i in range(6))
    fringe = 1.0 * ss
    reach = int(math.ceil(solid.max() + fringe)) + 1
    cells = big * big
    coverage = np.zeros(cells, np.float64)
    blocked = np.zeros(cells, np.float64)
    paint = np.zeros((3, cells), np.float64)
    along = np.zeros(cells, np.float64)
    ix, iy = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            px, py = ix + dx, iy + dy
            distance = np.hypot(px + 0.5 - x, py + 0.5 - y)
            weight = np.clip((solid + fringe - distance) / fringe, 0.0, 1.0)     # solid inside the ribbon, one soft pixel at its edge
            here = np.clip(weight * a, 0.0, 0.999)
            valid = (px >= 0) & (px < big) & (py >= 0) & (py < big) & (here > 1e-4)
            index = py[valid] * big + px[valid]
            h = here[valid]
            coverage += np.bincount(index, h, cells)
            blocked += np.bincount(index, -np.log(1.0 - h), cells)
            along += np.bincount(index, h * t[valid], cells)
            for ch in range(3):
                paint[ch] += np.bincount(index, colour[valid, ch] * h, cells)
    alpha = 1.0 - np.exp(-blocked)
    colour_px = paint / np.maximum(coverage, 1e-9)
    premultiplied = (colour_px * alpha).reshape(3, size, ss, size, ss).mean(axis=(2, 4))
    alpha_small = alpha.reshape(size, ss, size, ss).mean(axis=(1, 3))
    straight = (premultiplied / np.maximum(alpha_small, 1e-6)).transpose(1, 2, 0)
    t_map = (along.reshape(size, ss, size, ss).sum(axis=(1, 3)) / np.maximum(coverage.reshape(size, ss, size, ss).sum(axis=(1, 3)), 1e-9)).astype(np.float32)
    rgba = np.dstack([np.clip(straight, 0, 255), np.clip(alpha_small * 255, 0, 255)]).astype(np.uint8)
    return rgba, size, t_map


_enso_base = {}


def enso_precompute(radius, width):
    """Makes the base picture of a circle (about a third of a second); safe to call from a thread. Returns it."""
    key = (int(radius), round(width, 1))
    if key not in _enso_base:
        _enso_base[key] = enso_base(key[0], key[1])
    return _enso_base[key]


_enso_texture = {}


def draw_enso(canvas, cx, cy, radius, width, drawn=1.0, alpha=1.0, flame=True, color=PAPER, wait=True):
    """Draws the brush circle at (cx, cy). `drawn` (0 to 1) is how far the stroke has reached. A flame stroke warms from a soft red body to
    coral and amber tips; otherwise it is `color`, at `alpha` (the track behind a progress). Pictures are kept by their parameters: progress
    makes at most a hundred. With wait=False, nothing is drawn until the base picture is ready (it may be made by a thread)."""
    key = (int(radius), round(width, 1))
    if key not in _enso_base and not wait:
        return
    rgba, size, t_map = enso_precompute(radius, width)
    step = round(min(max(drawn, 0.0), 1.0) * 100)
    cache_key = (key, step, round(alpha * 100), flame, color)
    texture = _enso_texture.get(cache_key)
    if texture is None:
        if len(_enso_texture) > 220:
            _enso_texture.clear()
        image = rgba.copy()
        limit = step / 100.0
        if not flame:
            image[..., 0], image[..., 1], image[..., 2] = (color >> 16) & 255, (color >> 8) & 255, color & 255
        mask = 1.0 - _smooth(limit - 0.035, limit, t_map) if limit < 1.0 else 1.0
        image[..., 3] = np.clip(image[..., 3] * mask * alpha, 0, 255).astype(np.uint8)
        texture = _enso_texture[cache_key] = immvision.GlTexture(image)
    half = size / 2.0
    canvas.list.add_image(imgui.ImTextureRef(texture.texture_id), canvas.p(cx - half, cy - half), canvas.p(cx + half, cy + half))
