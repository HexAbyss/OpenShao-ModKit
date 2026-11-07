"""The ModKit window, in the launcher's visual identity: Extract, Compile, Verify and About pages, a footer, and the brush circle as the
progress of a long job."""
import json
import os
import threading
import time

from imgui_bundle import hello_imgui, imgui, immapp
from imgui_bundle import portable_file_dialogs as pfd

from .. import __version__
from . import art
from .art import DIM, EMBER, INK, MIST, MOSS, PAPER, REGULAR, SEMIBOLD, MEDIUM, WARNING, Canvas, rgb
from .tasks import Task, clock
from .widgets import button, header, item, link, row, switch, text_field

WIDTH, HEIGHT = 1040, 640
PAGES = ('Extract', 'Compile', 'Verify', 'About')
LICENSES = [('Dear ImGui', 'MIT'), ('imgui-bundle', 'MIT'), ('NumPy', 'BSD-3-Clause'), ('Pillow', 'MIT-CMU (HPND)'),
            ('Unicorn Engine', 'GPL-2.0'), ('rgbcx (bc7enc_rdo)', 'Public domain or MIT'), ('stb_dxt', 'Public domain or MIT'),
            ('Hanken Grotesk', 'SIL Open Font License 1.1'), ('Python', 'PSF License')]


def short(path):
    return path or ''


class App:
    def __init__(self, game='', out='', auto=None, limit=None, exit_when_done=False, page='Extract', pictures='', pack='', verify_file=''):
        self.page = page if page in PAGES else 'Extract'
        self.game, self.out = game, out                   # extraction
        self.limit = limit
        self.pictures, self.pack_file = pictures or out, pack  # compilation
        self.info = dict(name='', id='', version='1.0.0', authors='', summary='')
        self.logo = ''
        self.fast = False
        self.verify_file, self.verified = verify_file, None
        self.task, self.task_page = None, None
        self.last = None                                  # (page, kind, text lines) the outcome shown under a page's form
        self.dialog = None                                # (what, dialog): a native dialog that is open
        self.exit_when_done = exit_when_done
        self.frames = 0
        self.loaded_folder = None
        self.scroll_to_outcome = False
        threading.Thread(target=art.enso_precompute, args=(170, 34.0), daemon=True).start()   # the progress circle, ready before it is needed
        if self.pictures:
            self.load_project_info()
        if verify_file:
            self.page = 'Verify'
            self.start_verify()
        if auto == 'extract':
            self.start_extract()
        elif auto == 'compile':
            self.page = 'Compile'
            self.start_compile()

    # ---- native dialogs ----
    def pick(self, what):
        if self.dialog or self.busy:
            return
        if what == 'game':
            self.dialog = (what, pfd.open_file('Choose the game image', '', ['Disc images', '*.iso *.xiso', 'All files', '*']))
        elif what == 'pack':
            self.dialog = (what, pfd.save_file('Save the pack as', self.pack_file or 'MyPack.ostp', ['Texture packs', '*.ostp']))
        elif what in ('verify',):
            self.dialog = (what, pfd.open_file('Choose a texture pack', '', ['Texture packs', '*.ostp', 'All files', '*']))
        elif what == 'logo':
            self.dialog = (what, pfd.open_file('Choose the logo', '', ['Pictures', '*.png *.jpg *.jpeg *.bmp', 'All files', '*']))
        else:
            self.dialog = (what, pfd.select_folder('Choose a folder'))

    def poll_dialog(self):
        if not (self.dialog and self.dialog[1].ready(0)):
            return
        what, dialog = self.dialog
        self.dialog = None
        result = dialog.result()
        if not result:
            return
        value = result[0] if isinstance(result, (list, tuple)) else result
        if what == 'game':
            self.game = value
        elif what == 'out':
            self.out = value
            if not self.pictures:
                self.pictures = value
        elif what == 'pictures':
            self.pictures = value
            self.load_project_info()
        elif what == 'pack':
            self.pack_file = value if value.lower().endswith('.ostp') else value + '.ostp'
        elif what == 'logo':
            self.logo = value
        elif what == 'verify':
            self.verify_file = value
            self.start_verify()

    @property
    def busy(self):
        return self.task is not None and not self.task.finished

    # ---- jobs ----
    def start_extract(self):
        from ..textures.extract import extract
        game, out, limit = self.game.strip(), self.out.strip(), self.limit
        if not game or not out:
            self.last = ('Extract', 'error', ['Choose the game and a folder for the pictures first.'])
            return
        self.last = None

        def job(progress, cancel):
            return extract(game, out, limit=limit, progress=lambda done, total, textures: progress(done, total, textures), cancel=cancel)
        self.start('Extract', 'Extracting the textures', job)

    def load_project_info(self):
        """Fills the pack information from the pack.json of the chosen folder, when it has one"""
        try:
            with open(os.path.join(self.pictures, 'pack.json'), encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key in ('name', 'id', 'version', 'summary'):
            if isinstance(data.get(key), str):
                self.info[key] = data[key]
        if isinstance(data.get('authors'), list):
            self.info['authors'] = ', '.join(str(a) for a in data['authors'])
        if isinstance(data.get('logo'), str) and data['logo'] and os.path.isfile(os.path.join(self.pictures, data['logo'])):
            self.logo = os.path.join(self.pictures, data['logo'])

    def pack_information(self):
        info = dict(self.info)
        info['authors'] = [a.strip() for a in info['authors'].split(',') if a.strip()]
        info['min_recomp'] = '0.4.1'
        return info

    def start_compile(self):
        from ..textures.compile import compile_folder, read_preload
        folder, out = self.pictures.strip(), self.pack_file.strip()
        if not folder or not out:
            self.last = ('Compile', 'error', ['Choose the folder with the pictures and where to save the pack first.'])
            return
        info, logo, fast = self.pack_information(), self.logo.strip() or None, self.fast
        self.last = None
        try:  # keep the information beside the pictures, so the next time it is already filled in
            saved = dict(info, logo=os.path.basename(logo) if logo and os.path.dirname(logo) == folder else '')
            with open(os.path.join(folder, 'pack.json'), 'w', encoding='utf-8') as f:
                json.dump(saved, f, indent=2, ensure_ascii=False)
                f.write('\n')
        except OSError:
            pass

        def job(progress, cancel):
            return compile_folder(folder, out, info=info, logo=logo, preload=read_preload(folder), encoder='rgbcx:10' if fast else None,
                                  progress=lambda done, total: progress(done, total, None), cancel=cancel)
        self.start('Compile', 'Compiling the pack', job)

    def start_verify(self):
        from ..pack.reader import verify
        path = self.verify_file
        self.verified = None
        self.start('Verify', 'Checking the file', lambda progress, cancel: verify(path))

    def start(self, page, name, job):
        self.task, self.task_page, self.task_name = Task(name, job), page, name

    def collect(self):
        """When a job has just finished, turns its outcome into what the page shows"""
        t = self.task
        if not t or not t.finished or self.task_page is None:
            return
        page, self.task_page = self.task_page, None
        self.scroll_to_outcome = True
        if t.error:
            self.last = (page, 'error', [t.error])
        elif page == 'Extract':
            r = t.result
            if r.cancelled:
                self.last = (page, 'warning', ['Cancelled after %s.' % clock(t.elapsed), 'The pictures already written stay; no manifest was written.'])
            else:
                self.last = (page, 'ok', ['%d textures extracted in %s.' % (r.textures, clock(r.seconds)),
                                          'Edit the pictures in that folder, then try them in the game (Developer page) or compile them.'])
                self.pictures = self.pictures or self.out
                if not self.pictures:
                    self.pictures = self.out
        elif page == 'Compile':
            r = t.result
            if r.cancelled:
                self.last = (page, 'warning', ['Cancelled after %s. No pack was written.' % clock(t.elapsed)])
            else:
                lines = ['%d textures, %.1f MiB, in %s.' % (r.textures, r.size / 1048576, clock(r.seconds)),
                         'Checked against the format: %s.' % ('no problems' if r.verification.ok else 'PROBLEMS')]
                lines += ['Note: ' + w for w in r.warnings]
                lines.append('Install it from the Mods page of OpenShao with "Install from file".')
                self.last = (page, 'ok', lines)
        elif page == 'Verify':
            self.verified = t.result
        if self.exit_when_done:
            hello_imgui.get_runner_params().app_shall_exit = True

    # ---- drawing ----
    def gui(self):
        self.frames += 1
        self.poll_dialog()
        self.collect()
        vp = imgui.get_main_viewport()
        W, H = vp.size.x, vp.size.y
        imgui.set_next_window_pos(vp.pos)
        imgui.set_next_window_size(vp.size)
        flags = (imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_move | imgui.WindowFlags_.no_saved_settings |
                 imgui.WindowFlags_.no_bring_to_front_on_focus | imgui.WindowFlags_.no_scroll_with_mouse | imgui.WindowFlags_.no_background)
        imgui.begin('##modkit', None, flags)
        c = Canvas(imgui.get_window_draw_list(), (vp.pos.x, vp.pos.y))
        footer = H - 76
        working = self.busy and self.task_page == self.page and self.page in ('Extract', 'Compile')
        art.draw_background(c, W, H, W / 2, (96 + (footer - 96) / 2) if working else -80)
        self.top_bar(c, W)
        if working:
            self.working_view(c, W, footer)
        else:
            {'Extract': self.extract_page, 'Compile': self.compile_page, 'Verify': self.verify_page, 'About': self.about_page}[self.page](c, W, H)
        self.footer(c, W, H, working)
        imgui.end()

    def top_bar(self, c, W):
        x = W - 40
        xs = {}
        for name in reversed(PAGES):
            x -= c.measure(MEDIUM, 19, name)[0]
            xs[name] = x
            x -= 34
        for name in PAGES:
            width = c.measure(MEDIUM, 19, name)[0]
            hovered, clicked = item('tab-' + name, c, xs[name] - 8, 18, xs[name] + width + 8, 56)
            if clicked:
                self.page = name
            active = self.page == name
            c.text(MEDIUM, 19, xs[name], 28, rgb(PAPER if active or hovered else MIST), name)
            if active:
                c.brush_dash(xs[name] - 1, 50, width + 2)

    def footer(self, c, W, H, working):
        rule = H - 76
        c.rule(40, W - 40, rule)
        y = rule + 13
        right = W - 40
        if self.busy:
            c.list.add_circle_filled(c.p(46, y + 9), 4, rgb(WARNING))
            c.text(MEDIUM, 19, 60, y, rgb(PAPER), self.task_name)
            t = self.task
            if button('Cancel##footer', c, right - 96, rule + 6, right, rule + 38, 'Cancel', False, not t.cancel_requested):
                t.cancel()
            c.text_right(REGULAR, 19, right - 112, y, rgb(MIST), 'Cancelling...' if t.cancel_requested else
                         '%s elapsed, about %s left' % (clock(t.elapsed), clock(t.eta)))
        else:
            c.list.add_circle_filled(c.p(46, y + 9), 4, rgb(MOSS))
            c.text(MEDIUM, 19, 60, y, rgb(PAPER), 'Ready')
            c.text_right(REGULAR, 19, right, y, rgb(DIM), 'OpenShao ModKit %s' % __version__)

    def working_view(self, c, W, footer):
        t = self.task
        cx, cy = W / 2, 96 + (footer - 96) / 2
        radius = min(max((footer - 130) * 0.40, 90.0), 170.0)
        stroke = radius * 0.2
        art.glow(c, cx, cy, radius, 1.0)
        art.draw_enso(c, cx, cy, radius, stroke, 1.0, 0.09, False, PAPER, wait=False)
        art.draw_enso(c, cx, cy, radius, stroke, t.fraction, wait=False)
        c.text_centered(MEDIUM, 54, cx + 4, cy - 30, rgb(PAPER), '%d%%' % int(t.fraction * 100))
        if t.extra is not None:
            detail = '%d textures found' % t.extra
        else:
            detail = '%d of %d' % (t.done, t.total) if t.total else ''
        c.text_centered(REGULAR, 18.5, cx + 4, cy + 22, rgb(MIST), detail)

    def outcome(self, c, y, right, page):
        """What the last job of this page said, under its form"""
        if not self.last or self.last[0] != page:
            return y
        _, kind, lines = self.last
        c.rule(48, right, y)
        color = {'ok': MOSS, 'warning': WARNING, 'error': WARNING}[kind]
        yy = y + 22
        for i, line in enumerate(lines):
            c.text(MEDIUM if i == 0 else REGULAR, 19, 48, yy, rgb(color if i == 0 else MIST), line, right - 48)
            yy += c.measure(REGULAR, 19, line, right - 48)[1] + 10
        return yy

    # ---- pages ----
    def extract_page(self, c, W, H):
        header(c, 'Extract', 'Take the textures out of your own copy of the game.')
        right = W - 48
        y = 200
        row(c, y, right, 'Game', self.game or 'No game chosen', 1, MIST if self.game else DIM)
        if button('Choose##game', c, right - 84, y + 16, right, y + 50, 'Choose', False, not self.busy):
            self.pick('game')
        y += 60
        row(c, y, right, 'Folder', self.out or 'No folder chosen', 1, MIST if self.out else DIM)
        if button('Choose##out', c, right - 84, y + 16, right, y + 50, 'Choose', False, not self.busy):
            self.pick('out')
        y += 60
        c.rule(48, right, y)
        if button('Extract##go', c, 48, y + 24, 244, y + 66, 'Extract', True, not self.busy):
            self.start_extract()
        c.text(REGULAR, 19, 264, y + 35, rgb(DIM), 'Takes about 3 minutes. The game is only read; nothing of it is kept.')
        self.outcome(c, y + 90, right, 'Extract')

    def compile_page(self, c, W, H):
        header(c, 'Compile', 'Turn your edited pictures into a texture pack.')
        right = W - 48
        top = 200
        imgui.set_cursor_screen_pos(c.p(0, top))
        imgui.begin_child('##compile-list', (W, max(40.0, H - 76 - top - 8)), imgui.ChildFlags_.none, imgui.WindowFlags_.no_background)
        o = imgui.get_cursor_screen_pos()
        L = Canvas(imgui.get_window_draw_list(), (o.x, o.y))
        y = 0
        busy = self.busy
        row(L, y, right, 'Pictures', self.pictures or 'No folder chosen', 1, MIST if self.pictures else DIM)
        if button('Choose##pictures', L, right - 84, y + 16, right, y + 50, 'Choose', False, not busy):
            self.pick('pictures')
        y += 60
        row(L, y, right, 'Pack file', self.pack_file or 'Where to save the .ostp', 1, MIST if self.pack_file else DIM)
        if button('Choose##pack', L, right - 84, y + 16, right, y + 50, 'Choose', False, not busy):
            self.pick('pack')
        y += 60
        fields = (('name', 'Name', 'The name players see', 64), ('id', 'Id', 'Letters, digits, - or _ (no spaces)', 80),
                  ('version', 'Version', '1.0.0', 16), ('authors', 'Authors', 'Your name, separated by commas', 200),
                  ('summary', 'Summary', 'One sentence, up to 200 characters', 200))
        for key, label, hint, limit in fields:
            L.rule(48, right, y)
            L.text(SEMIBOLD, 20, 48, y + 25, rgb(PAPER), label)
            changed, value = text_field('f-' + key, L, 170, y + 11, right - 170, self.info[key], hint)
            if changed:
                self.info[key] = value[:limit]
            y += 60
        row(L, y, right, 'Logo', os.path.basename(self.logo) if self.logo else 'Optional, up to 256 x 256', 2, MIST if self.logo else DIM)
        if button('Choose##logo', L, right - 84, y + 16, right, y + 50, 'Choose', False, not busy):
            self.pick('logo')
        if button('Clear##logo', L, right - 180, y + 16, right - 96, y + 50, 'Clear', False, bool(self.logo) and not busy):
            self.logo = ''
        y += 60
        L.rule(48, right, y)
        L.text(SEMIBOLD, 20, 48, y + 25, rgb(PAPER), 'Quality')
        L.text(REGULAR, 19, 170, y + 25, rgb(MIST), 'Best takes minutes, once; Fast is for trying.')
        if button('Best##q', L, right - 192, y + 11, right - 100, y + 49, 'Best', not self.fast, not busy):
            self.fast = False
        if button('Fast##q', L, right - 88, y + 11, right, y + 49, 'Fast', self.fast, not busy):
            self.fast = True
        y += 60
        L.rule(48, right, y)
        if button('Compile##go', L, 48, y + 24, 244, y + 66, 'Compile', True, not busy):
            self.start_compile()
        y = self.outcome(L, y + 90, right, 'Compile')
        imgui.set_cursor_screen_pos(L.p(0, y + 24))   # the drawing above is not content to ImGui: say how far the page reaches
        imgui.dummy((1, 1))
        if self.scroll_to_outcome:                    # a job has just ended: bring what it said into view
            imgui.set_scroll_here_y(1.0)
            self.scroll_to_outcome = False
        imgui.end_child()

    def verify_page(self, c, W, H):
        header(c, 'Verify', 'Check that a texture pack follows the format.')
        right = W - 48
        y = 200
        row(c, y, right, 'Pack', self.verify_file or 'No file chosen', 1, MIST if self.verify_file else DIM)
        if button('Choose##verify', c, right - 84, y + 16, right, y + 50, 'Choose', False, not self.busy):
            self.pick('verify')
        y += 60
        c.rule(48, right, y)
        r = self.verified
        if self.last and self.last[0] == 'Verify':
            c.text(MEDIUM, 19, 48, y + 22, rgb(WARNING), self.last[2][0], right - 48)
        elif r is not None:
            info = r.info or {}
            if r.ok:
                c.text(MEDIUM, 19, 48, y + 22, rgb(MOSS), 'The file follows the format.')
                facts = [('Name', '%s %s' % (info.get('name', '?'), info.get('version', ''))), ('Id', info.get('id', '?')),
                         ('Textures', str(r.textures)), ('Size', '%.1f MiB' % (r.size / 1048576)),
                         ('Logo', '%dx%d' % r.logo if r.logo else 'none')]
                yy = y + 56
                for label, value in facts:
                    c.rule(48, right, yy)
                    c.text(SEMIBOLD, 20, 48, yy + 14, rgb(PAPER), label)
                    c.text(REGULAR, 19, 170, yy + 14, rgb(MIST), value)
                    yy += 46
            else:
                c.text(MEDIUM, 19, 48, y + 22, rgb(WARNING), 'The file has problems:')
                yy = y + 60
                for problem in r.problems[:12]:
                    c.text(REGULAR, 19, 48, yy, rgb(MIST), problem, right - 48)
                    yy += c.measure(REGULAR, 19, problem, right - 48)[1] + 8
        else:
            c.text(REGULAR, 19, 48, y + 22, rgb(MIST), 'Choose a .ostp file to check it, or a pack you just compiled.')

    def about_page(self, c, W, H):
        header(c, 'About', 'Version %s' % __version__)
        right = W - 48
        c.rule(48, right, 200)
        wrap = min(720.0, right - 48)
        c.text(REGULAR, 20, 48, 224, rgb(PAPER), 'The ModKit takes the textures out of your own copy of Mortal Kombat: Shaolin Monks and '
                                                   'turns the pictures you edit into texture packs for OpenShao. It contains no game files.', wrap)
        c.text(REGULAR, 19, 48, 296, rgb(MIST), 'It reads your game and keeps nothing of it. The decompression of the game\'s archive runs the game\'s own '
                                                  'routine, found in your copy, inside an emulator. The components it is built with:', wrap)
        half = (len(LICENSES) + 1) // 2
        name_w = [max(c.measure(MEDIUM, 18, n)[0] for n, _ in LICENSES[:half]), max(c.measure(MEDIUM, 18, n)[0] for n, _ in LICENSES[half:])]
        column = (right - 48) / 2
        for i, (name, license) in enumerate(LICENSES):
            side = i // half
            x, y = 48 + side * column, 380 + (i % half) * 30
            c.text(MEDIUM, 18, x, y, rgb(PAPER), name)
            c.text(REGULAR, 18, x + name_w[side] + 24, y, rgb(MIST), license)


def run(**options):
    app = App(**options)
    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = 'OpenShao ModKit'
    params.app_window_params.window_geometry.size = (WIDTH, HEIGHT)
    params.app_window_params.window_geometry.size_auto = False
    params.imgui_window_params.show_menu_bar = False
    params.imgui_window_params.default_imgui_window_type = hello_imgui.DefaultImGuiWindowType.no_default_window
    params.fps_idling.enable_idling = False
    params.callbacks.load_additional_fonts = art.load_fonts
    params.callbacks.setup_imgui_style = art.apply_style
    params.callbacks.show_gui = app.gui
    immapp.run(params)
    return 0
