"""The ModKit window. For now: choose the game, extract its textures with progress and cancelling."""
import os
import sys

from imgui_bundle import hello_imgui, imgui, immapp
from imgui_bundle import portable_file_dialogs as pfd

from .. import __version__
from .tasks import Task, clock

ACCENT = (0.36, 0.55, 0.95, 1.0)


class App:
    def __init__(self, game='', out='', auto=False, limit=None, exit_when_done=False):
        self.game, self.out = game, out
        self.limit = limit
        self.task = None
        self.message = ''
        self.dialog = None          # a native file dialog that is open: (kind, dialog)
        self.exit_when_done = exit_when_done
        self.frames = 0
        if auto:
            self.start_extract()

    # ---- jobs ----
    def start_extract(self):
        from ..textures.extract import extract
        game, out, limit = self.game.strip(), self.out.strip(), self.limit
        if not game or not out:
            self.message = 'Choose the game and a folder for the pictures first.'
            return
        self.message = ''

        def job(progress, cancel):
            return extract(game, out, limit=limit, progress=lambda done, total, textures: progress(done, total, textures), cancel=cancel)
        self.task = Task('Extracting the textures', job)

    # ---- drawing ----
    def pick(self, kind):
        if self.dialog:
            return
        if kind == 'game':
            self.dialog = (kind, pfd.open_file('Choose the game image', '', ['Disc images', '*.iso *.xiso', 'All files', '*']))
        else:
            self.dialog = (kind, pfd.select_folder('Choose a folder for the pictures'))

    def poll_dialog(self):
        if self.dialog and self.dialog[1].ready(0):
            kind, dialog = self.dialog
            self.dialog = None
            result = dialog.result()
            if kind == 'game' and result:
                self.game = result[0]
            elif kind == 'out' and result:
                self.out = result

    def path_row(self, label, value, kind, hint):
        imgui.text(label)
        imgui.set_next_item_width(imgui.get_content_region_avail().x - 110)
        _, value = imgui.input_text_with_hint('##' + kind, hint, value)
        imgui.same_line()
        if imgui.button('Browse...##' + kind, (100, 0)):
            self.pick(kind)
        return value

    def gui(self):
        self.frames += 1
        self.poll_dialog()
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 10))
        imgui.text_colored(ACCENT, 'OpenShao ModKit')
        imgui.same_line()
        imgui.text_disabled(__version__)
        imgui.separator()
        imgui.dummy((0, 6))
        imgui.text('1. Extract the textures of your copy of the game')
        imgui.text_disabled('The game is only read. Nothing of it is kept or sent anywhere.')
        busy = self.task is not None and not self.task.finished
        imgui.begin_disabled(busy)
        self.game = self.path_row('Game (disc image or folder)', self.game, 'game', 'path of the .iso, or of the folder with default.xbe')
        self.out = self.path_row('Folder for the pictures', self.out, 'out', 'an empty folder')
        if imgui.button('Extract', (140, 34)):
            self.start_extract()
        imgui.end_disabled()
        if self.message:
            imgui.text_colored((1.0, 0.45, 0.35, 1.0), self.message)
        self.task_panel()
        imgui.pop_style_var()
        if self.exit_when_done and self.task and self.task.finished and self.frames > 5:
            hello_imgui.get_runner_params().app_shall_exit = True

    def task_panel(self):
        t = self.task
        if not t:
            return
        imgui.dummy((0, 8))
        imgui.separator()
        imgui.text(t.name)
        if not t.finished:
            imgui.progress_bar(t.fraction, (-1, 22), '%.0f%%' % (100 * t.fraction))
            textures = ('%d textures found, ' % t.extra) if t.extra is not None else ''
            imgui.text_disabled('%d of %d archive entries, %s%s elapsed, about %s left' % (t.done, t.total, textures, clock(t.elapsed), clock(t.eta)))
            if t.cancel_requested:
                imgui.text('Cancelling...')
            elif imgui.button('Cancel', (110, 30)):
                t.cancel()
        elif t.error:
            imgui.text_colored((1.0, 0.45, 0.35, 1.0), t.error)
        else:
            r = t.result
            if r.cancelled:
                imgui.text('Cancelled after %s. The pictures already written stay; no manifest was written.' % clock(t.elapsed))
            else:
                imgui.text_colored((0.45, 0.85, 0.5, 1.0), '%d textures extracted in %s.' % (r.textures, clock(r.seconds)))
                imgui.text_disabled('Edit the pictures in that folder, then try them in the game (Developer page) or compile them into a pack.')


def run(**options):
    app = App(**options)
    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = 'OpenShao ModKit'
    params.app_window_params.window_geometry.size = (920, 560)
    params.imgui_window_params.show_menu_bar = False
    params.callbacks.show_gui = app.gui
    immapp.run(params)
    return 0
