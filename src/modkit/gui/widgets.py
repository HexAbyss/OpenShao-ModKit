"""Hand-drawn widgets (buttons, links, switch, rows, text field). Each is a rectangle in logical pixels: an invisible button gives the hit area
and hover state, and the shape is drawn into the window's draw list."""
from imgui_bundle import imgui

from . import art
from .art import DIM, EMBER, EMBER_HOVER, INK, LINE, LINK_HOVER, MEDIUM, MIST, PAPER, REGULAR, SEMIBOLD, SLATE, WARNING, rgb


def item(id, c, x0, y0, x1, y1):
    """(hovered, clicked) of a rectangle in logical pixels"""
    imgui.set_cursor_screen_pos(c.p(x0, y0))
    clicked = imgui.invisible_button(id, (max(1.0, x1 - x0), max(1.0, y1 - y0)))
    hovered = imgui.is_item_hovered()
    if hovered:
        imgui.set_mouse_cursor(imgui.MouseCursor_.hand)
    return hovered, clicked


def button(id, c, x0, y0, x1, y1, label, primary=False, enabled=True):
    imgui.begin_disabled(not enabled)
    hovered, clicked = item(id, c, x0, y0, x1, y1)
    imgui.end_disabled()
    alpha = 1.0 if enabled else 0.4
    if primary:
        c.rect(x0, y0, x1, y1, rgb(EMBER_HOVER if hovered else EMBER, alpha), 9)
    else:
        if hovered:
            c.rect(x0, y0, x1, y1, rgb(SLATE), 9)
        c.outline(x0, y0, x1, y1, rgb(DIM if hovered else LINE, alpha), 9)
    w, h = c.measure(SEMIBOLD, 19, label)
    c.text(SEMIBOLD, 19, (x0 + x1 - w) / 2, (y0 + y1 - h) / 2 - 0.5, rgb(INK if primary else PAPER, alpha), label)
    return clicked and enabled


def link(id, c, x, y, label, right_aligned=False, enabled=True):
    w, h = c.measure(MEDIUM, 19, label)
    x0 = x - w if right_aligned else x
    imgui.begin_disabled(not enabled)
    hovered, clicked = item(id, c, x0, y - 2, x0 + w, y + h + 2)
    imgui.end_disabled()
    c.text(MEDIUM, 19, x0, y, rgb((LINK_HOVER if hovered else EMBER) if enabled else DIM), label)
    return clicked and enabled


def switch(id, c, right, y, on):
    """A switch with its right edge at `right`; returns True when clicked"""
    hovered, clicked = item(id, c, right - 38, y, right, y + 22)
    c.toggle(right - 38, y, on, hovered)
    return clicked


def header(c, title, subtitle):
    c.text(SEMIBOLD, 36, 48, 104, rgb(PAPER), title)
    c.text(REGULAR, 20, 48, 148, rgb(MIST), subtitle)


def row(c, y, right, label, value, buttons=1, value_color=MIST, value_x=170):
    """A settings row: a rule, the label, the value (a long path is shortened in the middle) and room for `buttons` buttons on the right"""
    c.rule(48, right, y)
    c.text(SEMIBOLD, 20, 48, y + 25, rgb(PAPER), label)
    width = right - value_x - buttons * 96 - 16
    c.text(REGULAR, 19, value_x, y + 25, rgb(value_color), c.fit(REGULAR, 19, width, value))


def text_area(id, c, x, y, width, height, value, limit):
    """A multi-line text field, in the same style: (changed, value)"""
    imgui.set_cursor_screen_pos(c.p(x, y))
    imgui.push_font(art._fonts[REGULAR], 19)
    imgui.push_style_var(imgui.StyleVar_.frame_padding, (14, 8))
    imgui.push_style_var(imgui.StyleVar_.frame_border_size, 1.0)
    imgui.push_style_var(imgui.StyleVar_.frame_rounding, 9)
    changed, value = imgui.input_text_multiline('##' + id, value, (width, height), imgui.InputTextFlags_.none)
    hovered = imgui.is_item_hovered()
    imgui.pop_style_var(3)
    imgui.pop_font()
    if hovered:
        imgui.set_mouse_cursor(imgui.MouseCursor_.text_input)
    return changed, value[:limit]


def text_field(id, c, x, y, width, value, hint=''):
    """An ImGui text field styled to match the other widgets: (changed, value)"""
    imgui.set_cursor_screen_pos(c.p(x, y))
    imgui.set_next_item_width(width)
    imgui.push_font(art._fonts[REGULAR], 19)
    imgui.push_style_var(imgui.StyleVar_.frame_padding, (14, 8))
    imgui.push_style_var(imgui.StyleVar_.frame_border_size, 1.0)
    imgui.push_style_var(imgui.StyleVar_.frame_rounding, 9)
    changed, value = imgui.input_text_with_hint('##' + id, hint, value)
    hovered = imgui.is_item_hovered()
    imgui.pop_style_var(3)
    imgui.pop_font()
    if hovered:
        imgui.set_mouse_cursor(imgui.MouseCursor_.text_input)
    return changed, value
