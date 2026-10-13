"""HOLiZEK Windows desktop catalog: nonblocking import and source-preserving recipe browser."""
from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from .database import CatalogDB
from .media import synchronize_images
from .paths import module_paths

MONTHS = ('január','február','március','április','május','június','július','augusztus','szeptember','október','november','december')
DAYS = ('hétfő','kedd','szerda','csütörtök','péntek','szombat','vasárnap')


def version():
    try:
        return (Path(__file__).resolve().parent.parent/'VERSION').read_text('utf-8').strip()
    except OSError:
        return '—'


class Application(tk.Tk):
    def __init__(self, root_path: Path, mode='local', dsn=None):
        super().__init__()
        self.root_path = Path(root_path)
        self.paths = module_paths(root_path)
        self.mode = mode
        self.dsn = dsn
        self.db = None
        self.events = queue.Queue()
        self.current_recipe = None
        self.current_images = []
        self.preview_image = None
        self.started = None
        self.current_task = False
        self.title('HOLiZEK - HOLiNFORM')
        self.geometry('1500x900')
        self.minsize(960,620)
        self._load_geometry()
        self._init_theme()
        self._create_widgets()
        self.protocol('WM_DELETE_WINDOW',self._close)
        self.after(100,self._connect)
        self.after(250,self._poll_events)
        self.after(1000,self._clock)

    def _init_theme(self):
        try:
            from holinform_standards.design_runtime import apply_tk_theme, load_design
            apply_tk_theme(self, load_design().theme)
            return
        except Exception:
            # Neutral native fallback: the shared design runtime is optional for portable operation.
            try:
                ttk.Style(self).theme_use('clam')
            except tk.TclError:
                pass

    def _create_widgets(self):
        header = ttk.Frame(self,padding=(12,9,12,6))
        header.pack(fill='x')
        ttk.Label(header,text='HOLiZEK',font=('Segoe UI',17,'bold')).pack(anchor='w')
        sub = ttk.Frame(header)
        sub.pack(fill='x')
        self.version_text = ttk.Label(sub,text='Verzió: '+version(),font=('Segoe UI',9))
        self.version_text.pack(side='left',padx=(0,20))
        self.db_text = ttk.Label(sub,text='Adatbázis: nincs kapcsolat',font=('Segoe UI',9))
        self.db_text.pack(side='left',padx=(0,20))
        self.clock_text = ttk.Label(sub,text='',font=('Segoe UI',9))
        self.clock_text.pack(side='left')
        toolbar = ttk.Frame(self,padding=(12,6))
        toolbar.pack(fill='x')
        ttk.Label(toolbar,text='Keresés:').pack(side='left')
        self.search_var = tk.StringVar()
        self.search_box = ttk.Entry(toolbar,textvariable=self.search_var,width=32)
        self.search_box.pack(side='left',padx=(7,12))
        self.search_var.trace_add('write',self._defer_refresh)
        ttk.Label(toolbar,text='Kategória:').pack(side='left')
        self.category_var = tk.StringVar(value='Mindegyik')
        self.category_box = ttk.Combobox(toolbar,values=['Mindegyik'],textvariable=self.category_var,width=26,state='readonly')
        self.category_box.pack(side='left',padx=(7,12))
        self.category_box.bind('<<ComboboxSelected>>',lambda _e:self.refresh())
        self.import_button = ttk.Button(toolbar,text='Excel importálása',command=self.import_excel)
        self.import_button.pack(side='left',padx=4)
        self.images_button = ttk.Button(toolbar,text='Képek beolvasása',command=self.import_images)
        self.images_button.pack(side='left',padx=4)
        pane = ttk.Panedwindow(self,orient='horizontal')
        pane.pack(fill='both',expand=True,padx=12,pady=6)
        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left,weight=2)
        pane.add(right,weight=3)
        self.table = ttk.Treeview(left,columns=('title','category','duration'),show='headings',selectmode='browse')
        for key,label,w in [('title','Recept',330),('category','Kategória',170),('duration','Idő (perc)',90)]:
            self.table.heading(key,text=label,command=lambda col=key:self.sort_table(col))
            self.table.column(key,width=w,stretch=False,anchor='w' if key!='duration' else 'e')
        self.table.tag_configure('even')
        self.table.tag_configure('odd')
        yscroll = ttk.Scrollbar(left,orient='vertical',command=self.table.yview)
        xscroll = ttk.Scrollbar(left,orient='horizontal',command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set,xscrollcommand=xscroll.set)
        self.table.grid(row=0,column=0,sticky='nsew')
        yscroll.grid(row=0,column=1,sticky='ns')
        xscroll.grid(row=1,column=0,sticky='ew')
        left.rowconfigure(0,weight=1)
        left.columnconfigure(0,weight=1)
        self.table.bind('<<TreeviewSelect>>',self._select)
        self.table.bind('<Double-1>',self._show_selected)
        self.table.bind('<ButtonRelease-3>',self._popup)
        self.table.bind('<Button-1>',self._tree_separator_doubleclick,add='+')
        self.recipe_title = ttk.Label(right,text='Válassz receptet',font=('Segoe UI',13,'bold'),wraplength=700)
        self.recipe_title.pack(fill='x',padx=8,pady=6)
        self.recipe_metadata = ttk.Label(right,text='')
        self.recipe_metadata.pack(fill='x',padx=8,pady=2)
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill='both',expand=True,padx=6,pady=6)
        self.text_tabs = {}
        for caption in ('Hozzávalók','Előkészítés','Elkészítés'):
            frm = ttk.Frame(self.notebook)
            txt = tk.Text(frm,wrap='word',font=('Segoe UI',10),state='disabled',borderwidth=0)
            scroll = ttk.Scrollbar(frm,orient='vertical',command=txt.yview)
            txt.configure(yscrollcommand=scroll.set)
            txt.pack(side='left',expand=True,fill='both')
            scroll.pack(side='right',fill='y')
            self.notebook.add(frm,text=caption)
            self.text_tabs[caption] = txt
        media_frame = ttk.Frame(self.notebook)
        self.image_list = tk.Listbox(media_frame,height=8,activestyle='dotbox')
        self.image_list.pack(side='left',fill='both',expand=True,padx=5,pady=5)
        self.image_list.bind('<Double-Button-1>',self._open_image)
        self.image_list.bind('<<ListboxSelect>>',self._preview_image)
        media_side = ttk.Frame(media_frame)
        media_side.pack(side='left',fill='both',expand=True)
        self.image_preview = ttk.Label(media_side,text='Kép előnézete')
        self.image_preview.pack(expand=True)
        self.notebook.add(media_frame,text='Képek')
        bottom = ttk.Frame(self,padding=(12,5))
        bottom.pack(fill='x')
        self.progressbar = ttk.Progressbar(bottom,orient='horizontal',mode='determinate',maximum=100)
        self.progressbar.pack(side='right',fill='x',expand=False,padx=(12,0),ipadx=60)
        self.counter_label = ttk.Label(bottom,text='0 recept')
        self.counter_label.pack(side='right')
        self.status_label = ttk.Label(bottom,text='Indítás…')
        self.status_label.pack(side='left',expand=True,fill='x')

    def _load_geometry(self):
        try:
            settings = json.loads(self.paths['config'].read_text('utf-8'))
            geometry = settings.get('windows',{}).get('main',{}).get('geometry')
            if isinstance(geometry,str) and len(geometry)<80:
                self.geometry(geometry)
        except (OSError,ValueError,TypeError):
            pass

    def _save_geometry(self):
        config = self.paths['config']
        config.parent.mkdir(parents=True,exist_ok=True)
        temp = config.with_suffix('.tmp')
        temp.write_text(json.dumps({'windows':{'main':{'geometry':self.geometry()}}},ensure_ascii=False,indent=2),'utf-8')
        temp.replace(config)

    def _clock(self):
        now = datetime.now().astimezone()
        self.clock_text.configure(text=f'{now.year}. {MONTHS[now.month-1]} {now.day}., {DAYS[now.weekday()]} {now:%H:%M:%S}')
        self.after(1000,self._clock)

    def _connect(self):
        try:
            self.db = CatalogDB(self.root_path,self.mode,self.dsn)
            self.db_text.configure(text=self.db.status_label)
            self._reload_categories()
            self.refresh()
            self.status_label.configure(text='Készen áll. A képek a HOLiNFORM import/HOLiZEK mappájából tölthetők be.')
        except Exception as ex:
            self.status_label.configure(text='Adatbázis hiba: '+str(ex))
            messagebox.showerror('HOLiZEK - Adatbázishiba - HOLiNFORM',str(ex))

    def _reload_categories(self):
        self.category_box.configure(values=['Mindegyik']+[c for c,_ in self.db.categories()])

    def _defer_refresh(self,*_):
        if getattr(self,'search_job',None):
            self.after_cancel(self.search_job)
        self.search_job = self.after(160,self.refresh)

    def refresh(self):
        if not self.db:
            return
        rows = self.db.search(self.search_var.get(),'' if self.category_var.get()=='Mindegyik' else self.category_var.get())
        self.table.delete(*self.table.get_children())
        for idx,(rid,title,category,duration) in enumerate(rows):
            self.table.insert('', 'end',iid=rid,values=(title,category,duration if duration is not None else '—'),tags=('even' if idx%2==0 else 'odd',))
        self.counter_label.configure(text=f'{len(rows)} recept / összesen {self.db.count()}')

    def sort_table(self,col):
        rows=[(self.table.set(i,col),i) for i in self.table.get_children('')]
        direction=getattr(self,'_sorting',None)
        desc=direction==(col,False)
        if col=='duration':
            rows.sort(key=lambda r:int(r[0]) if r[0].isdigit() else 99999,reverse=desc)
        else:
            rows.sort(key=lambda r:r[0].casefold(),reverse=desc)
        for index,(_v,item) in enumerate(rows):
            self.table.move(item,'',index)
        self._sorting=(col,desc)

    def _tree_separator_doubleclick(self,event):
        # Width adjustment belongs only to the actual heading separator, never to row cells.
        if self.table.identify_region(event.x,event.y)=='separator' and self.table.identify_region(event.x,event.y-1)=='separator':
            return

    def _popup(self,event):
        iid=self.table.identify_row(event.y)
        if not iid:return
        self.table.selection_set(iid)
        menu=tk.Menu(self,tearoff=False)
        menu.add_command(label='Recept címének másolása',command=lambda:self.clipboard_append(self.table.set(iid,'title')))
        menu.add_command(label='Szűrés erre a címre',command=lambda:self.search_var.set(self.table.set(iid,'title')))
        menu.tk_popup(event.x_root,event.y_root)

    def _select(self,_event=None):
        if not self.db:return
        ids=self.table.selection()
        if not ids:return
        self.current_recipe=ids[0]
        info=self.db.recipe(ids[0])
        if not info:return
        title,url,category,duration,ingredients,prep,steps=info
        self.recipe_title.configure(text=title)
        self.recipe_metadata.configure(text=f'{category}    |    {duration}    |    {url}')
        for caption,body in [('Hozzávalók',ingredients),('Előkészítés',prep),('Elkészítés',steps)]:
            widget=self.text_tabs[caption]
            widget.configure(state='normal')
            widget.delete('1.0','end')
            widget.insert('1.0',body or '(nincs adat)')
            widget.configure(state='disabled')
        self.current_images=self.db.images(ids[0])
        self.image_list.delete(0,'end')
        for seq,source_path,stored,remote,state in self.current_images:
            self.image_list.insert('end',f'{seq}. {Path(source_path.replace(chr(92),"/")).name or "(névtelen)"}  [{state}]')
        self.image_preview.configure(text=f'{len(self.current_images)} képhivatkozás',image='')
        self.preview_image=None

    def _show_selected(self,event):
        if self.table.identify_region(event.x,event.y)=='cell':
            self._select()

    def _preview_image(self,_event=None):
        selected=self.image_list.curselection()
        if not selected:return
        row=self.current_images[selected[0]]
        stored=row[2]
        if not stored:
            self.image_preview.configure(image='',text='Ez a kép még nincs beolvasva.')
            return
        path=self.paths['image_store']/stored
        try:
            from PIL import Image,ImageTk
            im=Image.open(path)
            im.thumbnail((330,290))
            self.preview_image=ImageTk.PhotoImage(im)
            self.image_preview.configure(image=self.preview_image,text='')
        except Exception:
            self.image_preview.configure(image='',text='Az előnézethez Pillow szükséges; duplán kattintva megnyitható.')

    def _open_image(self,_event=None):
        chosen=self.image_list.curselection()
        if not chosen:return
        stored=self.current_images[chosen[0]][2]
        if not stored:return
        target=self.paths['image_store']/stored
        if not target.is_file():return
        if os.name=='nt':os.startfile(str(target))
        else:subprocess.Popen(['xdg-open',str(target)])

    def _start_task(self,operation,fn):
        if self.current_task or not self.db:return
        self.current_task=True
        self.import_button.configure(state='disabled')
        self.images_button.configure(state='disabled')
        self.started=time.monotonic()
        self.progressbar.configure(value=0)
        def progress(message,done,total):
            self.events.put(('progress',message,done,total))
        def runner():
            try:
                # A separate SQL connection prevents cross-thread access to live GUI's cursor.
                backend=CatalogDB(self.root_path,self.mode,self.dsn)
                try:result=fn(backend,progress)
                finally:backend.close()
                self.events.put(('done',operation,result))
            except Exception as ex:
                self.events.put(('error',operation,str(ex)))
        threading.Thread(target=runner,daemon=True).start()

    def _poll_events(self):
        try:
            while True:
                e=self.events.get_nowait()
                if e[0]=='progress':
                    _typ,message,done,total=e
                    ratio=done/max(total,1)
                    elapsed=time.monotonic()-self.started if self.started else 0
                    eta=elapsed/ratio-elapsed if ratio>0 else 0
                    self.progressbar.configure(value=max(0,min(100,ratio*100)))
                    self.status_label.configure(text=f'{message}: {done}/{total} · {ratio:.0%} · ETA {max(0,int(eta))} s')
                elif e[0]=='done':
                    self.current_task=False
                    self.import_button.configure(state='normal')
                    self.images_button.configure(state='normal')
                    self.progressbar.configure(value=100)
                    self._reload_categories()
                    self.refresh()
                    self.status_label.configure(text=f'{e[1]}: {e[2]}')
                    if self.current_recipe and self.table.exists(self.current_recipe):
                        self.table.selection_set(self.current_recipe)
                        self._select()
                elif e[0]=='error':
                    self.current_task=False
                    self.import_button.configure(state='normal')
                    self.images_button.configure(state='normal')
                    self.status_label.configure(text='Hiba: '+e[2])
                    messagebox.showerror('HOLiZEK - Importálási hiba - HOLiNFORM',e[2])
        except queue.Empty:
            pass
        self.after(250,self._poll_events)

    def import_excel(self):
        file=filedialog.askopenfilename(title='HOLiZEK - Recept Excel kiválasztása - HOLiNFORM',filetypes=[('Excel','*.xlsx')])
        if file:self._start_task('Excel import',lambda db,report:db.import_workbook(file,report))

    def import_images(self):
        source=self.paths['image_import']
        if not source.is_dir():
            source.mkdir(parents=True,exist_ok=True)
        self._start_task('Képimport',lambda db,report:synchronize_images(db,source,report))

    def _close(self):
        if self.current_task:
            messagebox.showwarning('HOLiZEK - Folyamatban lévő import - HOLiNFORM','Az import befejezéséig ne zárd be az alkalmazást.')
            return
        self._save_geometry()
        if self.db:self.db.close()
        self.destroy()
