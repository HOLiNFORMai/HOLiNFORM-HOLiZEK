"""HOLiZEK desktop recipe browser, following shared HOLiNFORM GUI contracts.

The catalog preserves the original imported recipes; this interface does not
make medical/allergen claims. Long imports and database initialization run off
Tk's event thread. Widgets are updated on the Tk thread only.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font, ttk
from urllib.parse import urlparse

from .database import CatalogDB
from .media import synchronize_images
from .paths import module_paths

MODULE_ID = "HOLiNFORM-HOLiZEK"
MONTHS = ('január', 'február', 'március', 'április', 'május', 'június',
          'július', 'augusztus', 'szeptember', 'október', 'november', 'december')
DAYS = ('hétfő', 'kedd', 'szerda', 'csütörtök', 'péntek', 'szombat', 'vasárnap')
HEADINGS = {'title': 'Recept', 'category': 'Kategória', 'duration': 'Idő (perc)'}


def version() -> str:
    try:
        return (Path(__file__).resolve().parent.parent / 'VERSION').read_text(
            encoding='utf-8').strip()
    except OSError:
        return '—'


def ordered_items(items, column: str, descending: bool = False):
    """Sort search result tuples consistently (including missing durations)."""
    if column == 'duration':
        return sorted(items, key=lambda row: (
            row[3] is None, -(row[3] or 0) if descending else (row[3] or 0),
            row[1].casefold()))
    index = {'title': 1, 'category': 2}.get(column, 1)
    return sorted(items, key=lambda row: (str(row[index] or '').casefold(),
                   row[1].casefold()), reverse=descending)


def safe_http_url(value: str) -> str | None:
    try:
        p = urlparse(value.strip())
        return value.strip() if p.scheme.lower() in ('https', 'http') and p.netloc else None
    except ValueError:
        return None


class Application(tk.Tk):
    def __init__(self, root_path: Path, mode: str = 'local', dsn=None):
        super().__init__()
        self.root_path = Path(root_path)
        self.paths = module_paths(self.root_path)
        self.mode, self.dsn = mode, dsn
        self.db = None
        self.events = queue.Queue()
        self.current_recipe = None
        self.current_url = ''
        self.current_images = []
        self.preview_image = None
        self.current_task = False
        self.started = None
        self.search_job = None
        self._sort_column = 'title'
        self._sort_descending = False
        self._result_rows = []
        self._normal_geometry = None
        self._theme = {}
        self._watch_stop = None
        self._version_stop = None
        self._closed = False
        self.title('HOLiZEK - HOLiNFORM')
        self._init_theme()
        self._restore_geometry()
        self._create_widgets()
        self.bind('<Configure>', self._record_geometry, add='+')
        self.bind('<Control-f>', lambda _e: self._focus_search(), add='+')
        self.bind('<F5>', lambda _e: self.refresh(), add='+')
        self.protocol('WM_DELETE_WINDOW', self._close)
        self._connect_async()
        self.after(90, self._poll_events)
        self._clock()

    def _init_theme(self):
        try:
            from holinform_standards.design_runtime import (
                apply_tk_icon, apply_tk_theme, load_design, watch_tk_design)
            snapshot = load_design(self.root_path)
            self._theme = snapshot.theme
            apply_tk_theme(self, self._theme)
            apply_tk_icon(self, MODULE_ID, self.root_path)
            self._watch_stop = watch_tk_design(
                self, self._theme_changed, root=self.root_path)
        except Exception:
            # First launch without Standards: native Windows theme fallback.
            try:
                ttk.Style(self).theme_use('clam')
            except tk.TclError:
                pass

    def _theme_changed(self, snapshot):
        self._theme = snapshot.theme
        try:
            from holinform_standards.design_runtime import apply_tk_theme, apply_tk_icon
            apply_tk_theme(self, snapshot.theme)
            apply_tk_icon(self, MODULE_ID, self.root_path)
        except Exception:
            return
        self._theme_text_widgets()
        self._update_table_row_colors()

    def _theme_text_widgets(self):
        colors = self._theme.get('colors') or {}
        fonts = self._theme.get('fonts') or {}
        base_font = (fonts.get('ui_family', 'Segoe UI'), int(fonts.get('ui_size', 10)))
        for widget in getattr(self, 'text_tabs', {}).values():
            widget.configure(font=base_font)
            if colors.get('table_foreground') and colors.get('table_background'):
                widget.configure(background=colors['table_background'],
                                 foreground=colors['table_foreground'],
                                 insertbackground=colors['table_foreground'])
        if hasattr(self, 'image_list') and colors.get('table_foreground') and colors.get('table_background'):
            self.image_list.configure(
                background=colors['table_background'],
                foreground=colors['table_foreground'],
                selectbackground=colors.get('table_selection_background',
                                            colors.get('accent', colors['table_background'])))

    def _update_table_row_colors(self):
        colors = self._theme.get('colors') or {}
        even = colors.get('table_background')
        odd = colors.get('table_alternate_background')
        if even:
            self.table.tag_configure('even', background=even)
        if odd:
            self.table.tag_configure('odd', background=odd)

    def _create_widgets(self):
        header = ttk.Frame(self, padding=(14, 9, 14, 6))
        header.pack(fill='x')
        ttk.Label(header, text='HOLiZEK  ·  Receptkatalógus',
                  font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        meta = ttk.Frame(header)
        meta.pack(fill='x')
        ttk.Label(meta, text='Verzió: ' + version(), font=('Segoe UI', 9)).pack(side='left')
        self.db_text = ttk.Label(meta, text='Adatbázis: —', font=('Segoe UI', 9))
        self.db_text.pack(side='left', padx=(14, 14))
        self.clock_text = ttk.Label(meta, text='', font=('Segoe UI', 9))
        self.clock_text.pack(side='left')
        try:
            from holinform_standards.version_notice import attach_tk_version_notice
            self._version_stop = attach_tk_version_notice(
                self, meta, MODULE_ID, version(), root=self.root_path)
        except Exception:
            pass

        toolbar = ttk.Frame(self, padding=(14, 4, 14, 6))
        toolbar.pack(fill='x')
        search_line = ttk.Frame(toolbar)
        search_line.pack(fill='x', pady=(0, 5))
        ttk.Label(search_line, text='Keresés:').pack(side='left')
        self.search_var = tk.StringVar()
        self.search_box = ttk.Entry(search_line, textvariable=self.search_var, width=40)
        self.search_box.pack(side='left', padx=(7, 14))
        self.search_var.trace_add('write', self._defer_refresh)
        self.search_box.bind('<Button-3>', self._entry_context_menu)
        ttk.Label(search_line, text='Ebben:').pack(side='left')
        self.scope_var = tk.StringVar(value='Recept neve')
        self.scope_box = ttk.Combobox(search_line, textvariable=self.scope_var,
            values=('Recept neve', 'Hozzávalók', 'Minden szöveg'), state='readonly', width=17)
        self.scope_box.pack(side='left', padx=(7, 14))
        self.scope_box.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        ttk.Label(search_line, text='Kategória:').pack(side='left')
        self.category_var = tk.StringVar(value='Mindegyik')
        self.category_box = ttk.Combobox(search_line, textvariable=self.category_var,
                                         values=('Mindegyik',), state='readonly', width=26)
        self.category_box.pack(side='left', padx=(7, 10))
        self.category_box.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        ttk.Button(search_line, text='Szűrés törlése', command=self._clear_filters).pack(side='left')

        actions = ttk.Frame(toolbar)
        actions.pack(fill='x')
        self.import_button = ttk.Button(actions, text='Excel importálása', command=self.import_excel)
        self.import_button.pack(side='left', padx=(0, 7))
        self.images_button = ttk.Button(actions, text='Képek beolvasása', command=self.import_images)
        self.images_button.pack(side='left', padx=(0, 7))
        ttk.Button(actions, text='Képmappa megnyitása', command=self.open_image_folder).pack(side='left', padx=(0, 7))
        ttk.Button(actions, text='Recept másolása', command=self.copy_recipe).pack(side='left', padx=(0, 7))
        ttk.Button(actions, text='Forrás megnyitása', command=self.open_source).pack(side='left')

        pane = ttk.Panedwindow(self, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=14, pady=(3, 7))
        left, right = ttk.Frame(pane), ttk.Frame(pane)
        pane.add(left, weight=5)
        pane.add(right, weight=6)

        self.table = ttk.Treeview(left, columns=tuple(HEADINGS), show='headings',
                                  selectmode='browse', style='Treeview')
        for col, width in (('title', 400), ('category', 240), ('duration', 100)):
            self.table.column(col, width=width, minwidth=70, stretch=False,
                              anchor='e' if col == 'duration' else 'w')
        self._update_sort_headings()
        yscroll = ttk.Scrollbar(left, orient='vertical', command=self.table.yview)
        xscroll = ttk.Scrollbar(left, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.table.bind('<<TreeviewSelect>>', self._select)
        self.table.bind('<Double-Button-1>', self._table_doubleclick)
        self.table.bind('<Button-3>', self._popup)
        self._update_table_row_colors()

        heading = ttk.Frame(right, padding=(8, 3, 8, 4))
        heading.pack(fill='x')
        self.recipe_title = ttk.Label(heading, text='Válassz receptet',
                                      font=('Segoe UI', 14, 'bold'), wraplength=620)
        self.recipe_title.pack(anchor='w', fill='x')
        self.recipe_metadata = ttk.Label(heading, text='A bal oldali listából választhatsz.')
        self.recipe_metadata.pack(anchor='w', fill='x', pady=(4, 0))
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill='both', expand=True, padx=6, pady=(4, 0))
        self.text_tabs = {}
        for caption in ('Áttekintés', 'Hozzávalók', 'Előkészítés', 'Elkészítés'):
            frame = ttk.Frame(self.notebook)
            edit = tk.Text(frame, wrap='word', font=('Segoe UI', 10),
                           state='disabled', borderwidth=0, padx=14, pady=12)
            scroll = ttk.Scrollbar(frame, orient='vertical', command=edit.yview)
            edit.configure(yscrollcommand=scroll.set)
            edit.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
            self.notebook.add(frame, text=caption)
            self.text_tabs[caption] = edit
        media_frame = ttk.Frame(self.notebook)
        media_frame.columnconfigure(1, weight=3)
        media_frame.columnconfigure(0, weight=2)
        media_frame.rowconfigure(0, weight=1)
        self.image_list = tk.Listbox(media_frame, activestyle='dotbox', exportselection=False)
        self.image_list.grid(row=0, column=0, sticky='nsew', padx=6, pady=6)
        self.image_list.bind('<Double-Button-1>', self._open_image)
        self.image_list.bind('<<ListboxSelect>>', self._preview_image)
        image_panel = ttk.Frame(media_frame)
        image_panel.grid(row=0, column=1, sticky='nsew')
        self.image_preview = ttk.Label(image_panel, text='A kép előnézete', anchor='center')
        self.image_preview.pack(expand=True, fill='both')
        self.notebook.add(media_frame, text='Képek (0)')
        self._theme_text_widgets()

        footer = ttk.Frame(self, padding=(14, 5, 14, 8))
        footer.pack(fill='x')
        self.status_label = ttk.Label(footer, text='Adatbázis megnyitása…')
        self.status_label.pack(side='left', fill='x', expand=True)
        self.counter_label = ttk.Label(footer, text='0 recept')
        self.counter_label.pack(side='right', padx=(10, 0))
        self.progressbar = ttk.Progressbar(footer, mode='determinate', maximum=100, length=180)
        # Invisible outside work; no decorative 0% bar on idle.

    def _clock(self):
        if self._closed:
            return
        now = datetime.now().astimezone()
        self.clock_text.configure(text=(f'{now.year}. {MONTHS[now.month-1]} '
                     f'{now.day}., {DAYS[now.weekday()]} {now:%H:%M:%S}'))
        self.after(1000, self._clock)

    def _restore_geometry(self):
        w = min(1920, max(900, self.winfo_screenwidth() - 70))
        h = min(1000, max(610, self.winfo_screenheight() - 95))
        w = min(w, self.winfo_screenwidth())
        h = min(h, self.winfo_screenheight())
        self.geometry(f'{w}x{h}+0+0')
        self.minsize(min(940, w), min(620, h))
        try:
            raw = json.loads(self.paths['config'].read_text(encoding='utf-8'))
            item = raw.get('windows', {}).get('main', {})
            # Read both canonical rect and V1 geometry without trusting offscreen coords.
            geo = item.get('geometry')
            if isinstance(geo, str) and 'x' in geo:
                import re
                match = re.fullmatch(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)', geo)
                if match:
                    ww, hh, xx, yy = (int(v) for v in match.groups())
                else:
                    ww, hh, xx, yy = w, h, 0, 0
            else:
                ww, hh = int(item.get('width', w)), int(item.get('height', h))
                xx, yy = int(item.get('x', 0)), int(item.get('y', 0))
            ww = min(max(500, ww), self.winfo_screenwidth())
            hh = min(max(420, hh), self.winfo_screenheight())
            xx = max(0, min(xx, self.winfo_screenwidth() - ww))
            yy = max(0, min(yy, self.winfo_screenheight() - hh))
            self.geometry(f'{ww}x{hh}+{xx}+{yy}')
            if item.get('window_state') == 'maximized' and os.name == 'nt':
                self.after(80, lambda: self.state('zoomed'))
        except (OSError, ValueError, TypeError, OverflowError):
            pass

    def _record_geometry(self, event):
        if event.widget is self and self.state() == 'normal':
            self._normal_geometry = self.geometry()

    def _save_geometry(self):
        import re
        p = self.paths['config']
        try:
            data = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
            if not isinstance(data, dict):
                data = {}
            item = data.setdefault('windows', {}).setdefault('main', {})
            geom = self._normal_geometry or self.geometry()
            m = re.fullmatch(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)', geom)
            if m:
                w, h, x, y = (int(v) for v in m.groups())
                item.update(geometry=geom, width=w, height=h, x=x, y=y)
            item['window_state'] = 'maximized' if self.state() == 'zoomed' else 'normal'
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(tmp, p)
        except (OSError, ValueError, TypeError, tk.TclError):
            pass

    def _connect_async(self):
        self.progressbar.configure(mode='indeterminate')
        self.progressbar.pack(side='right', padx=(12, 0), before=self.counter_label)
        self.progressbar.start(14)
        def worker():
            try:
                opened = CatalogDB(self.root_path, self.mode, self.dsn)
                self.events.put(('connected', opened))
            except Exception as exc:
                self.events.put(('connection_error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _publish_database(self):
        if self.db is None:
            return
        try:
            from holinform_standards.database_indicator import publish
            publish(MODULE_ID, 'postgresql' if self.db.server else 'sqlite',
                    self.db.host if self.db.server else None, root=self.root_path)
        except Exception:
            pass

    def _reload_categories(self):
        previous = self.category_var.get()
        categories = [v for v, _count in self.db.categories()]
        choices = ['Mindegyik', *categories]
        self.category_box.configure(values=choices)
        if previous not in choices:
            self.category_var.set('Mindegyik')

    def _defer_refresh(self, *_):
        if self.search_job:
            self.after_cancel(self.search_job)
        self.search_job = self.after(180, self.refresh)

    def _entry_context_menu(self, event):
        entry = event.widget
        menu = tk.Menu(self, tearoff=False)
        for title, action in (('Másolás', '<<Copy>>'),
                              ('Kivágás', '<<Cut>>'),
                              ('Beillesztés', '<<Paste>>'),
                              ('Mind kijelölése', '<<SelectAll>>')):
            if title == 'Mind kijelölése':
                command = lambda: entry.selection_range(0, 'end')
            else:
                command = lambda symbol=action: entry.event_generate(symbol)
            menu.add_command(label=title, command=command)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            menu.destroy()

    def _clear_filters(self):
        self.search_var.set('')
        self.category_var.set('Mindegyik')
        self.scope_var.set('Recept neve')
        self.refresh()

    def _focus_search(self):
        self.search_box.focus_set()
        self.search_box.selection_range(0, 'end')
        return 'break'

    def refresh(self):
        if self.search_job:
            self.after_cancel(self.search_job)
            self.search_job = None
        if not self.db:
            return
        previous = self.current_recipe
        scope = {'Recept neve': 'title', 'Hozzávalók': 'ingredients',
                 'Minden szöveg': 'all'}.get(self.scope_var.get(), 'title')
        try:
            rows = self.db.search(self.search_var.get(),
                '' if self.category_var.get() == 'Mindegyik' else self.category_var.get(),
                scope=scope)
            self._result_rows = ordered_items(rows, self._sort_column, self._sort_descending)
            # Diff-like batch refresh; sorting is kept across every filter change.
            old = self.table.get_children('')
            if old:
                self.table.delete(*old)
            for idx, (rid, title, category, duration) in enumerate(self._result_rows):
                self.table.insert('', 'end', iid=rid, values=(title, category,
                                  duration if duration is not None else '—'),
                                  tags=('even' if idx % 2 == 0 else 'odd',))
            count = self.db.count()
            self.counter_label.configure(text=f'{len(rows)} / {count} recept')
            if previous and self.table.exists(previous):
                self.table.selection_set(previous)
                self.table.see(previous)
            else:
                self.current_recipe = None
                self._clear_detail()
        except Exception as exc:
            self.status_label.configure(text='Lekérdezési hiba: ' + str(exc))

    def sort_table(self, col):
        if self._sort_column == col:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column, self._sort_descending = col, False
        self._update_sort_headings()
        self.refresh()

    def _update_sort_headings(self):
        for col, name in HEADINGS.items():
            arrow = (' ▼' if self._sort_descending else ' ▲') if col == self._sort_column else ''
            self.table.heading(col, text=name + arrow,
                               command=lambda chosen=col: self.sort_table(chosen))

    def _table_doubleclick(self, event):
        if self.table.identify_region(event.x, event.y) == 'separator':
            column = self.table.identify_column(event.x)
            if column:
                index = int(column[1:]) - 1
                columns = tuple(HEADINGS)
                if 0 <= index < len(columns):
                    self._fit_column(columns[index])
            return 'break'
        if self.table.identify_region(event.x, event.y) == 'cell':
            self._select()
        return None

    def _fit_column(self, col):
        style = ttk.Style(self)
        family = style.lookup('Treeview', 'font') or 'TkFixedFont'
        try:
            f = font.nametofont(family)
        except tk.TclError:
            f = font.Font(self, font=family)
        widths = [f.measure(HEADINGS[col] + ' ▲') + 26]
        for item in self.table.get_children(''):
            widths.append(f.measure(str(self.table.set(item, col))) + 22)
        self.table.column(col, width=min(max(widths), 1200), stretch=False)

    def _popup(self, event):
        iid = self.table.identify_row(event.y)
        if not iid:
            return
        self.table.selection_set(iid)
        self._select()
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label='Recept címének másolása',
                         command=lambda: self._copy(self.table.set(iid, 'title')))
        menu.add_command(label='Teljes recept másolása', command=self.copy_recipe)
        menu.add_command(label='Szűrés erre a címre',
                         command=lambda: self.search_var.set(self.table.set(iid, 'title')))
        menu.add_command(label='Szűrés erre a kategóriára',
                         command=lambda: self._filter_category(iid))
        menu.add_separator()
        menu.add_command(label='Recept forrása a böngészőben', command=self.open_source)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            menu.destroy()

    def _filter_category(self, iid):
        candidates = [s.strip() for s in self.table.set(iid, 'category').split('|') if s.strip()]
        allowed = self.category_box.cget('values')
        for candidate in candidates:
            if candidate in allowed:
                self.category_var.set(candidate)
                self.refresh()
                break

    def _clear_detail(self):
        self.current_url = ''
        self.current_images = []
        self.preview_image = None
        self.recipe_title.configure(text='Válassz receptet')
        self.recipe_metadata.configure(text='Nincs kiválasztott recept.')
        for edit in self.text_tabs.values():
            self._set_text(edit, '')
        self.image_list.delete(0, 'end')
        self.image_preview.configure(text='A kép előnézete', image='')
        self.notebook.tab(4, text='Képek (0)')

    @staticmethod
    def _set_text(edit, content):
        edit.configure(state='normal')
        edit.delete('1.0', 'end')
        edit.insert('1.0', content or '(nincs adat)')
        edit.configure(state='disabled')
        edit.yview_moveto(0)

    def _select(self, _event=None):
        if not self.db:
            return
        selected = self.table.selection()
        if not selected:
            return
        rid = selected[0]
        data = self.db.recipe(rid)
        if not data:
            return
        self.current_recipe = rid
        title, url, category, duration, ingredients, prep, instructions = data
        self.current_url = url
        self.recipe_title.configure(text=title)
        self.recipe_metadata.configure(text=f'{category}  ·  {duration or "Idő: nincs adat"}')
        sections = [('HOZZÁVALÓK', ingredients), ('ELŐKÉSZÍTÉS', prep),
                    ('ELKÉSZÍTÉS', instructions)]
        overview = '\n\n'.join(f'{name}\n\n{text or "(nincs adat)"}' for name, text in sections)
        self._set_text(self.text_tabs['Áttekintés'], overview)
        for tab, body in [('Hozzávalók', ingredients), ('Előkészítés', prep),
                          ('Elkészítés', instructions)]:
            self._set_text(self.text_tabs[tab], body)
        self.current_images = self.db.images(rid)
        self.image_list.delete(0, 'end')
        for seq, source_path, stored, _remote, state in self.current_images:
            filename = Path(source_path.replace('\\', '/')).name or '(névtelen)'
            self.image_list.insert('end', f'{seq}. {filename}  [{state}]')
        self.preview_image = None
        self.image_preview.configure(text=f'{len(self.current_images)} képhivatkozás', image='')
        self.notebook.tab(4, text=f'Képek ({len(self.current_images)})')
        if self.current_images:
            self.image_list.selection_set(0)
            self._preview_image()

    def _preview_image(self, _event=None):
        selected = self.image_list.curselection()
        if not selected:
            return
        stored = self.current_images[selected[0]][2]
        self.preview_image = None
        if not stored:
            self.image_preview.configure(image='', text='A képfájl még nincs beolvasva.')
            return
        path = self.paths['image_store'] / stored
        try:
            from PIL import Image, ImageOps, ImageTk
            with Image.open(path) as original:
                picture = ImageOps.exif_transpose(original)
                picture.thumbnail((610, 610))
                self.preview_image = ImageTk.PhotoImage(picture)
            self.image_preview.configure(image=self.preview_image, text='')
        except Exception:
            self.image_preview.configure(image='', text='A kép nem olvasható, vagy a Pillow hiányzik.')

    def _open_image(self, _event=None):
        selected = self.image_list.curselection()
        if not selected:
            return
        stored = self.current_images[selected[0]][2]
        if stored:
            self._open_directory(self.paths['image_store'] / stored)

    def _open_directory(self, path: Path):
        if not path.exists():
            self._dialog('Figyelmeztetés', f'Nem található:\n{path}')
            return
        try:
            if os.name == 'nt':
                os.startfile(str(path))
            else:
                subprocess.Popen(['xdg-open', str(path)])
        except OSError as exc:
            self._dialog('Hiba', str(exc))

    def open_image_folder(self):
        p = self.paths['image_import'] / 'haztartas_ma_export' / 'images'
        p.mkdir(parents=True, exist_ok=True)
        self._open_directory(p)

    def _copy(self, content: str):
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_label.configure(text='Vágólapra másolva.')

    def copy_recipe(self):
        if not self.db or not self.current_recipe:
            return
        record = self.db.recipe(self.current_recipe)
        if not record:
            return
        title, source, category, duration, ingredients, prep, steps = record
        self._copy('\n\n'.join((title, f'{category} | {duration}',
                'HOZZÁVALÓK\n' + (ingredients or ''),
                'ELŐKÉSZÍTÉS\n' + (prep or ''),
                'ELKÉSZÍTÉS\n' + (steps or ''), source)))

    def open_source(self):
        url = safe_http_url(self.current_url)
        if not url:
            self._dialog('Figyelmeztetés', 'Ehhez a recepthez nincs megnyitható webcím.')
            return
        webbrowser.open(url)

    def _start_task(self, operation, fn):
        if self.current_task or not self.db:
            return
        self.current_task = True
        self.import_button.configure(state='disabled')
        self.images_button.configure(state='disabled')
        self.started = time.monotonic()
        self.progressbar.stop()
        self.progressbar.configure(mode='determinate', value=0)
        self.progressbar.pack(side='right', padx=(12, 0), before=self.counter_label)

        def progress(message, done, total):
            self.events.put(('progress', message, done, total))
        def worker():
            try:
                backend = CatalogDB(self.root_path, self.mode, self.dsn)
                try:
                    result = fn(backend, progress)
                finally:
                    backend.close()
                self.events.put(('done', operation, result))
            except Exception as exc:
                self.events.put(('error', operation, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_progress(self):
        self.current_task = False
        self.import_button.configure(state='normal')
        self.images_button.configure(state='normal')
        self.progressbar.stop()
        self.progressbar.pack_forget()

    def _poll_events(self):
        if self._closed:
            return
        try:
            for _ in range(120):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == 'connected':
                    self.db = event[1]
                    self.db_text.configure(text=self.db.status_label)
                    self.progressbar.stop()
                    self.progressbar.pack_forget()
                    self._publish_database()
                    self._reload_categories()
                    self.refresh()
                    self.status_label.configure(text='Készen áll.')
                elif kind == 'connection_error':
                    self.progressbar.stop()
                    self.progressbar.pack_forget()
                    self.status_label.configure(text='Adatbázishiba: ' + event[1])
                    self._dialog('Adatbázishiba', event[1])
                elif kind == 'progress':
                    _, message, done, total = event
                    ratio = min(1.0, max(0.0, done / max(total, 1)))
                    elapsed = time.monotonic() - self.started if self.started else 0
                    eta = round(elapsed * (1 - ratio) / ratio) if ratio > 0 else None
                    self.progressbar.configure(value=ratio * 100)
                    self.status_label.configure(text=(f'{message}: {done}/{total}  ·  '
                        f'{ratio:.0%}  ·  {elapsed:.0f} s  ·  '
                        + (f'ETA {eta} s' if eta is not None else 'ETA —')))
                elif kind == 'done':
                    self._finish_progress()
                    self._reload_categories()
                    self.refresh()
                    self.status_label.configure(text=f'{event[1]} kész: {event[2]}')
                    if self.current_recipe and self.table.exists(self.current_recipe):
                        self.table.selection_set(self.current_recipe)
                        self._select()
                elif kind == 'error':
                    self._finish_progress()
                    self.status_label.configure(text=f'{event[1]} hiba: {event[2]}')
                    self._dialog('Importálási hiba', event[2])
        except queue.Empty:
            pass
        self.after(90, self._poll_events)

    def import_excel(self):
        if self.current_task or not self.db:
            return
        path = filedialog.askopenfilename(
            title='HOLiZEK - Recept Excel kiválasztása - HOLiNFORM',
            filetypes=[('Excel munkafüzet', '*.xlsx')])
        if path:
            self._start_task('Excel import', lambda db, report: db.import_workbook(path, report))

    def import_images(self):
        if self.current_task or not self.db:
            return
        source = self.paths['image_import']
        source.mkdir(parents=True, exist_ok=True)
        self._start_task('Képimport', lambda db, report: synchronize_images(db, source, report))

    def _dialog(self, title: str, content: str):
        dialog = tk.Toplevel(self)
        dialog.title(f'HOLiZEK - {title} - HOLiNFORM')
        dialog.transient(self)
        dialog.resizable(True, False)
        body = ttk.Frame(dialog, padding=22)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=title, font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(body, text=content, wraplength=560, justify='left').pack(
            anchor='w', fill='x', pady=(10, 16))
        ttk.Button(body, text='Rendben', command=dialog.destroy).pack(anchor='e')
        dialog.update_idletasks()
        w, h = max(380, dialog.winfo_reqwidth()), max(145, dialog.winfo_reqheight())
        xx = self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2)
        yy = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 2)
        dialog.geometry(f'{w}x{h}+{xx}+{yy}')
        dialog.grab_set()
        dialog.focus_set()

    def _close(self):
        if self.current_task:
            self._dialog('Folyamatban lévő import',
                         'Az adatimport befejezéséig az alkalmazás nem zárható be.')
            return
        self._closed = True
        self._save_geometry()
        for stop in (self._watch_stop, self._version_stop):
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass
        if self.db:
            self.db.close()
        self.destroy()
