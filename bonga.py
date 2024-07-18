import io
import logging
import os
import socket
import sys
import time
import traceback
from collections import deque
from concurrent.futures.thread import ThreadPoolExecutor
from threading import Thread
from tkinter import Tk, Button, ttk, W, E, Image, Label, Menu, DISABLED, NORMAL, END, HORIZONTAL, \
    Checkbutton, BooleanVar, BOTH, Toplevel, Frame, Listbox, LEFT, Scrollbar, RIGHT, SINGLE, VERTICAL, Y, StringVar, \
    Entry
from urllib.parse import urlparse

import clipboard
import requests
from PIL import Image, ImageTk
from requests import RequestException
from requests.compat import urljoin

USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:68.0) Gecko/20100101 Firefox/68.0'
REFERER = 'https://bimbolive.com/'

HEADERS = {
    'User-agent': USER_AGENT,
    'Referer': REFERER
}

TIMEOUT = (3.05, 9.05)
DELAY = 2000
PAD = 5
MAX_FAILS = 6
OUTPUT = os.path.join(os.path.expanduser("~"), "tmp")
LOGS = "./logs/"

ALL_TIME = 0
DAY = 24 * 60 * 60
TWO_DAYS = 2 * DAY
WEEK = 7 * DAY
MONTH = 30 * DAY
THREE_MONTHS = 3 * MONTH

PLAYER_HOST = 'localhost'
PLAYER_PORT = 8686

executor = ThreadPoolExecutor(max_workers=20)

root = Tk()


class MainWindow:

    def __init__(self):
        global root

        self.http_session = requests.Session()
        self.http_session.headers.update(HEADERS)

        self.menu_bar = Menu(root)
        self.menu_bar.add_command(label="Back", command=self.back_in_history)
        self.menu_bar.add_command(label="Toggle image", command=self.toggle_image)

        hist_menu = Menu(self.menu_bar, tearoff=0)
        hist_menu.add_command(label="All time", command=lambda: self.show_full_history(ALL_TIME))
        hist_menu.add_command(label="Last day", command=lambda: self.show_full_history(DAY))
        hist_menu.add_command(label="Two days", command=lambda: self.show_full_history(TWO_DAYS))
        hist_menu.add_command(label="Week", command=lambda: self.show_full_history(WEEK))
        hist_menu.add_command(label="Month", command=lambda: self.show_full_history(MONTH))
        hist_menu.add_command(label="Three months", command=lambda: self.show_full_history(THREE_MONTHS))
        self.menu_bar.add_cascade(label="History", menu=hist_menu)

        self.menu_bar.add_command(label="Link", command=self.copy_model_link)

        root.config(menu=self.menu_bar)

        self.session = None
        self.show_image = False
        self.hist_window = None
        self.proxies = None

        self.model_name = None
        self.update_title()

        self.level = 0

        self.image_label = Label(root)

        self.level += 1
        self.cb_model = ttk.Combobox(root, width=30, justify=RIGHT)
        self.cb_model.bind("<FocusIn>", self.focus_callback)
        self.cb_model.bind("<Button-1>", self.drop_down_callback)
        self.cb_model.bind('<Return>', self.enter_callback)
        self.cb_model.focus_set()
        self.cb_model.grid(row=self.level, column=0, columnspan=3, sticky=W + E, padx=PAD, pady=PAD)

        self.btn_remove = Button(root, text="-", command=self.remove_from_favorites)
        self.btn_remove.grid(row=self.level, column=3, sticky=W + E, padx=PAD, pady=PAD)

        self.level += 1
        self.btn_update = Button(root, text="Update info", command=lambda: self.update_model_info(True))
        self.btn_update.grid(row=self.level, column=0, sticky=W + E, padx=PAD, pady=PAD)

        self.btn_show_recording = Button(root, text="SRM", command=self.show_recording_model, state=DISABLED)
        self.btn_show_recording.grid(row=self.level, column=1, sticky=W + E, padx=PAD, pady=PAD)

        self.btn_play = Button(root, text="Play", command=self.play_record)
        self.btn_play.grid(row=self.level, column=2, sticky=W + E, padx=PAD, pady=PAD)

        self.use_proxy = BooleanVar()
        self.use_proxy.set(False)
        self.use_proxy.trace('w', self.on_use_proxy_change)

        self.chk_use_proxy = Checkbutton(root, text='Use proxy', variable=self.use_proxy, state=DISABLED)
        # self.chk_use_proxy.grid(row=self.level, column=1, sticky=W, padx=PAD, pady=PAD)

        self.cb_proxy = ttk.Combobox(root, width=30, state=DISABLED)
        # self.cb_proxy.grid(row=self.level, column=2, columnspan=3, sticky=W + E, padx=PAD, pady=PAD)

        self.level += 1
        self.btn_start = Button(root, text="Start", command=self.on_btn_start)
        self.btn_start.grid(row=self.level, column=0, sticky=W + E, padx=PAD, pady=PAD)

        self.btn_stop = Button(root, text="Stop", command=self.on_btn_stop, state=DISABLED)
        self.btn_stop.grid(row=self.level, column=1, sticky=W + E, padx=PAD, pady=PAD)

        self.copy_button = Button(root, text="Copy", command=self.copy_model_name)
        self.copy_button.grid(row=self.level, column=2, sticky=W + E, padx=PAD, pady=PAD)

        self.paste_button = Button(root, text="Paste", command=self.paste_model_name)
        self.paste_button.grid(row=self.level, column=3, columnspan=2, sticky=W + E, padx=PAD, pady=PAD)

        self.level += 1
        self.progress = ttk.Progressbar(root, orient=HORIZONTAL, length=120, mode='indeterminate')

        root.bind("<FocusIn>", self.focus_callback)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.play_list_url = None
        self.base_url = None
        self.model_image = None
        self.img_url = None
        self.img_counter = 0

        self.hist_logger = logging.getLogger('history')
        self.hist_logger.setLevel(logging.INFO)

        self.fh_hist = logging.FileHandler(os.path.join(LOGS, f'hist_{int(time.time())}.log'))
        self.fh_hist.setLevel(logging.INFO)
        self.hist_logger.addHandler(self.fh_hist)

        self.proxy_logger = logging.getLogger('proxy')
        self.proxy_logger.setLevel(logging.INFO)

        self.fh_proxy = logging.FileHandler(os.path.join(LOGS, f'proxy_{int(time.time())}.log'))
        self.fh_proxy.setLevel(logging.INFO)
        self.proxy_logger.addHandler(self.fh_proxy)

        # self.proxy_dict = {}
        # self.load_proxy_dict()

        self.hist_stack = []

        self.load_image()

    def on_btn_start(self):
        self.btn_start.config(state=DISABLED)

        self.stop()

        success = self.update_model_info(True)
        if not success:
            self.set_default_state()
            return

        self.session = RecordSession(self, self.base_url, self.model_name, "chunks.m3u8")
        self.session.start()

        self.btn_stop.config(state=NORMAL)
        self.btn_show_recording.config(state=NORMAL)
        self.progress.grid(row=self.level, column=0, columnspan=5, sticky=W + E, padx=PAD, pady=PAD)
        self.progress.start()

        self.update_title()

        root.configure(background='green')

    def on_btn_stop(self):
        self.stop()
        self.set_default_state()

    def stop(self):
        if self.session is None:
            return

        self.session.stop()
        self.session = None

    def copy_model_name(self):
        clipboard.copy(self.cb_model.get())

    def paste_model_name(self):
        self.cb_model.set(clipboard.paste())
        self.cb_model.selection_range(0, END)

    def copy_model_link(self):
        clipboard.copy(urljoin(self.base_url, 'playlist.m3u8'))

    def play_record(self):
        if self.session is None:
            return

        clipboard.copy(self.session.output_dir)
        executor.submit(send_to_player, self.session.output_dir)

    def update_model_info(self, remember):
        self.img_counter = 0
        if remember and (self.model_name is not None):
            if len(self.hist_stack) == 0 or (self.model_name != self.hist_stack[-1]):
                self.hist_stack.append(self.model_name)

        self.set_undefined_state()

        input_url = self.cb_model.get().strip()

        if len(input_url) == 0:
            self.set_undefined_state()
            return False

        proxy = self.cb_proxy.get().strip()
        if self.use_proxy.get() and len(proxy.strip()) != 0:
            self.proxies = {
                "http": "http://" + proxy,
                "https": "https://" + proxy
            }
        else:
            self.proxies = None

        self.base_url = None
        if input_url.startswith('https://ded'):
            public_pos = input_url.rfind('public')
            self.base_url = input_url[: public_pos + 7]

            self.model_name = self.extract_model_name(self.base_url)
        elif input_url.startswith('https://live-edge'):
            slash_pos = input_url[: -1].rfind('/')
            self.base_url = input_url[: slash_pos + 1]

            self.model_name = self.extract_model_name(self.base_url)
        elif input_url.startswith('http'):
            slash_pos = input_url[: -1].rfind('/')
            self.model_name = input_url[slash_pos + 1: -1] if input_url.endswith('/') else input_url[slash_pos + 1:]
        else:
            self.model_name = input_url

        if self.base_url is None:
            self.base_url = self.get_model_baseurl()

        if self.base_url is None:
            info = self.get_model_info()
            print(info)
            if ('localData' not in info) or ('videoServerUrl' not in info['localData']):
                self.set_undefined_state()
                return False

            if info['performerData']['isAway']:
                self.set_undefined_state()
                return False

            server_url = info['localData']['videoServerUrl']
            self.model_name = info['performerData']['username']
            self.base_url = f"https:{server_url}/hls/stream_{self.model_name}/public-aac/stream_{self.model_name}/"

        if self.get_chunks() is None:
            self.set_undefined_state()
            return False

        if self.use_proxy.get() and len(proxy) != 0:
            self.add_to_proxies(proxy)

        self.get_image_url()
        self.add_to_history(self.model_name)

        self.update_title()

        return True

    def add_to_history(self, name):
        if name not in self.cb_model['values']:
            self.cb_model['values'] = (name, *self.cb_model['values'])

        self.hist_logger.info(name)

    def remove_from_favorites(self):
        name = self.cb_model.get().strip()
        values = list(self.cb_model['values'])
        if name not in values:
            return

        values.remove(name)
        self.cb_model['values'] = tuple(values)
        if len(values) == 0:
            self.cb_model.set('')
        else:
            self.cb_model.set(values[0])

    def add_to_proxies(self, proxy):
        if len(self.cb_proxy['values']) == 0:
            self.cb_proxy['values'] = proxy
        elif proxy not in self.cb_proxy['values']:
            self.cb_proxy['values'] = (proxy, *self.cb_proxy['values'])

        self.proxy_logger.info(proxy)
        count = self.proxy_dict.get(proxy, 0)
        self.proxy_dict[proxy] = count + 1

    def focus_callback(self, event):
        self.cb_model.selection_range(0, END)
        if self.hist_window is not None:
            self.hist_window.lift()

    def drop_down_callback(self, event):
        self.cb_model.focus_set()
        self.cb_model.selection_range(0, END)
        self.cb_model.event_generate('<Down>')

    def enter_callback(self, event):
        self.update_model_info(True)

    def extract_model_name(self, url):
        if url is None:
            return None

        stream_pos = url.find('stream_')
        slash_pos = url.find('/', stream_pos)

        return url[stream_pos + 7: slash_pos]

    def get_image_url(self):
        edge_pos = self.base_url.find('-edge')
        point_pos = self.base_url.find('.', edge_pos)
        vsid = self.base_url[edge_pos + 5: point_pos]
        if vsid[-3:] == '-rn':
            vsid = vsid[:-3]
        self.img_url = f"https://mobile-edge{vsid}.bcvcdn.com/stream_{self.model_name}.jpg"

    def get_model_info(self):
        post_fields = {
            'method': 'getRoomData',
            'args[]': [self.model_name, "", ""]
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest'
        }

        try:
            response = self.http_session.post("https://rf.chat-s-devushkami.com/tools/amf.php?x-country=a1",
                                              data=post_fields,
                                              headers=headers,
                                              proxies=self.proxies,
                                              timeout=TIMEOUT)
        except RequestException as error:
            print("GetRoomData exception model: " + self.model_name)
            print(error)
            traceback.print_exc()
            return {}

        return response.json()

    def get_model_baseurl(self):
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Host': 'sex-videochat.club',
            'Origin': 'https://sex-videochat.club',
            'Referer': f'https://sex-videochat.club/chat/{self.model_name}/'
        }

        try:
            response = self.http_session.post(f"https://sex-videochat.club/bonga/model-data/{self.model_name}/",
                                              headers=headers,
                                              proxies=self.proxies,
                                              timeout=TIMEOUT)
        except RequestException as error:
            print("GetRoomData exception model: " + self.model_name)
            print(error)
            traceback.print_exc()
            return None

        playlist_url = response.text
        domain = urlparse(playlist_url).netloc
        if len(domain) < 1:
            print(f'Playlist : {playlist_url}')
            return None

        self.model_name = self.extract_model_name(playlist_url)
        return f"https://{domain}/hls/stream_{self.model_name}/public-aac/stream_{self.model_name}/"

    def load_image(self):
        global executor
        global root

        self.img_counter += 1
        if (self.img_url is not None or self.img_counter % 30 == 0) and self.show_image and (self.model_name is not None):
            executor.submit(self.fetch_image)

        root.update_idletasks()
        root.after(DELAY, self.load_image)

    def fetch_image(self):
        global root

        try:
            if self.img_counter % 30 == 0:
                self.base_url = self.get_model_baseurl()

                if self.base_url is None:
                    info = self.get_model_info()
                    print(info)
                    if ('localData' not in info) or ('videoServerUrl' not in info['localData']):
                        raise ValueError(f"Model {self.model_name} is offline.")

                    if info['performerData']['isAway']:
                        raise ValueError(f"Model {self.model_name} is away.")

                    server_url = info['localData']['videoServerUrl']
                    self.model_name = info['performerData']['username']
                    self.base_url = f"https:{server_url}/hls/stream_{self.model_name}/public-aac/stream_{self.model_name}/"
                if self.get_chunks() is None:
                    raise ValueError(f"Model {self.model_name} is offline!")
                self.get_image_url()

            response = self.http_session.get(self.img_url, timeout=TIMEOUT)
            img = Image.open(io.BytesIO(response.content))
            w, h = img.size
            k = 200 / w
            img_resized = img.resize((200, int(h * k)), resample=Image.Resampling.NEAREST, reducing_gap=1.0)
            root.after_idle(self.update_image, img_resized)
        except BaseException as error:
            print(f"Image URL: {self.img_url}")
            print(error)
            traceback.print_exc()
            self.img_url = None
            self.model_image = None
            self.img_counter = 0

    def update_image(self, img):
        self.model_image = ImageTk.PhotoImage(img)
        self.image_label.config(image=self.model_image)

    def on_close(self):
        global root

        self.stop()
        root.update_idletasks()
        root.destroy()
        self.fh_hist.close()
        self.hist_logger.removeHandler(self.fh_hist)
        self.fh_proxy.close()
        self.proxy_logger.removeHandler(self.fh_proxy)
        self.http_session.close()

    def set_default_state(self):
        global root

        self.session = None
        self.btn_stop.config(state=DISABLED)
        self.btn_start.config(state=NORMAL)
        self.btn_show_recording.config(state=DISABLED)
        self.progress.stop()
        self.progress.grid_forget()
        self.update_title()
        root.configure(background='SystemButtonFace')

    def update_title(self):
        global root

        root.title(self.model_name or '<Undefined>')

        if self.session is None:
            return

        if not self.session.is_alive():
            return

        if self.session.model_name != root.title():
            return

        root.title(root.title() + " - Recording")

    def set_undefined_state(self):
        self.model_image = None
        self.image_label.config(image=None)
        self.model_name = None
        self.img_url = None
        self.update_title()

    def show_recording_model(self):
        if self.session is None:
            return

        self.cb_model.set(self.session.model_name)
        self.cb_model.selection_range(0, END)
        self.update_model_info(True)

    def on_use_proxy_change(self, *args):
        if self.use_proxy.get():
            self.cb_proxy.config(state=NORMAL)
            self.cb_proxy.focus_set()
            self.cb_proxy.selection_range(0, END)
        else:
            self.cb_proxy.config(state=DISABLED)

    def toggle_image(self):
        if self.show_image:
            self.model_image = None
            self.image_label.config(image=None)
            self.img_url = None
            self.image_label.grid_forget()
            self.show_image = False
        else:
            self.show_image = True
            self.image_label.grid(row=0, column=0, columnspan=5, sticky=W + E, padx=PAD, pady=PAD)
            self.update_model_info(True)

    def show_full_history(self, period):
        if self.hist_window is not None:
            self.hist_window.on_close()

        self.menu_bar.entryconfig("History", state=DISABLED)
        hist_future = executor.submit(load_hist_dict, period)
        hist_future.add_done_callback(lambda f: root.after_idle(self.show_hist_window, f))

    def show_hist_window(self, future):
        history = future.result()
        self.hist_window = HistoryWindow(self, Toplevel(root), history)
        self.menu_bar.entryconfig("History", state=NORMAL)

    def back_in_history(self):
        if len(self.hist_stack) == 0:
            return

        self.cb_model.set(self.hist_stack.pop())
        self.update_model_info(False)

    def load_proxy_dict(self):
        for file in os.listdir(LOGS):
            if not file.startswith('proxy_'):
                continue

            full_path = os.path.join(LOGS, file)
            if os.path.getsize(full_path) == 0:
                continue

            with open(full_path) as f:
                for line in f.readlines():
                    name = line.strip()
                    count = self.proxy_dict.get(name, 0)
                    self.proxy_dict[name] = count + 1

        hist = sorted(self.proxy_dict.items(), key=lambda x: x[1], reverse=True)
        self.cb_proxy.configure(values=[x[0] for x in hist[:10]])

    def get_chunks(self):
        try:
            chunks_url = urljoin(self.base_url, "chunks.m3u8")
            r = self.http_session.get(chunks_url, timeout=TIMEOUT)
            lines = r.text.splitlines()

            if len(lines) < RecordSession.MIN_CHUNKS:
                return None

            return Chunks(lines)
        except RequestException:
            return None


def load_hist_dict(period):
    now = time.time()

    res = {}
    for file in os.listdir(LOGS):
        if not file.startswith('hist_'):
            continue

        full_path = os.path.join(LOGS, file)
        if os.path.getsize(full_path) == 0:
            continue

        mtime = os.path.getmtime(full_path)
        diff = now - mtime

        if (period != ALL_TIME) and (diff > period):
            continue

        with open(full_path) as f:
            for line in f.readlines():
                name = line.strip()
                count = res.get(name, 0)
                res[name] = count + 1

    return res


def send_to_player(path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((PLAYER_HOST, PLAYER_PORT))
        sock.sendall(bytes(path + "\n", 'ascii'))


class HistoryWindow:

    def __init__(self, parent, win, hist_dict):
        self.window = win
        self.parent_window = parent
        self.hist_dict = hist_dict
        self.window.title("Full history")
        self.window.resizable(False, False)

        frm_top = Frame(win)
        frm_bottom = Frame(win)

        self.search = StringVar()
        self.search.trace("w", lambda name, index, mode, sv=self.search: self.on_search(sv))
        self.entry_search = Entry(frm_top, textvariable=self.search, width=57)
        self.entry_search.pack(side=LEFT, fill=BOTH, expand=1)

        self.btn_clear = Button(frm_top, text="Clear", command=self.on_clear)
        self.btn_clear.pack(side=RIGHT, fill=BOTH, expand=1)

        self.list_box = Listbox(frm_bottom, width=60, height=40, selectmode=SINGLE)
        self.list_box.pack(side=LEFT, fill=BOTH, expand=1)
        scroll = Scrollbar(frm_bottom, command=self.list_box.yview, orient=VERTICAL)
        scroll.pack(side=RIGHT, fill=Y)
        self.list_box.config(yscrollcommand=scroll.set)
        self.list_box.bind('<<ListboxSelect>>', self.on_listbox_select)

        frm_top.pack()
        frm_bottom.pack()

        self.window.bind("<FocusIn>", self.focus_callback)
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        self.fill_list_box()

    def on_clear(self):
        self.search.set("")
        self.on_search(self.search)

    def on_search(self, search):
        query = search.get().strip().lower()
        if len(query) < 2:
            self.fill_list_box()
            return

        self.list_box.delete(0, END)
        search_results = []
        for key in self.hist_dict:
            pos = key.lower().find(query)
            if pos == -1:
                continue

            search_results.append((key, pos))

        search_results.sort(key=lambda x: x[1])
        self.list_box.insert(END, *[x[0] for x in search_results])

    def fill_list_box(self):
        self.list_box.delete(0, END)
        hist = sorted(self.hist_dict.items(), key=lambda x: x[1], reverse=True)
        self.list_box.insert(END, *[x[0] for x in hist])

    def on_listbox_select(self, event):
        w = event.widget
        selected = w.curselection()
        if len(selected) == 0:
            return

        index = selected[0]
        value = w.get(index)
        self.parent_window.cb_model.set(value)

    def lift(self):
        self.window.lift()

    def on_close(self):
        self.parent_window.hist_window = None
        self.window.update_idletasks()
        self.window.destroy()

    def focus_callback(self, event):
        self.entry_search.selection_range(0, END)
        root.lift()


class SessionPool:

    def __init__(self, count):
        self.size = count
        self.data = []
        self.current = 0
        for i in range(self.size):
            s = requests.Session()
            s.headers.update(HEADERS)
            self.data.append(s)

    def get(self):
        s = self.data[self.current]
        self.current += 1
        self.current %= self.size
        return s


POOL = SessionPool(5)


class Chunks:
    IDX_CUR_POS = 3

    def __init__(self, lines):
        self.ts = [line for line in lines if not line.startswith("#")]
        self.cur_pos = int(lines[Chunks.IDX_CUR_POS].split(':')[1])


class RecordSession(Thread):
    MIN_CHUNKS = 6

    def __init__(self, main_win, url_base, model, chunk_url):
        super(RecordSession, self).__init__()

        self.http_session = requests.Session()
        self.http_session.headers.update(HEADERS)

        self.main_win = main_win
        self.base_url = url_base
        self.model_name = model
        self.output_dir = os.path.join(OUTPUT, self.model_name + '_' + str(int(time.time())))
        os.mkdir(self.output_dir)

        self.chunks_url = urljoin(self.base_url, chunk_url)
        self.name = 'RecordSession'
        self.stopped = False
        self.daemon = True
        self.file_num = 1
        self.file_deq = deque(maxlen=4)

        self.logger = logging.getLogger('bonga_application')
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[%(asctime)s] %(threadName)s:%(funcName)s > %(message)s')

        self.fh = logging.FileHandler(os.path.join(self.output_dir, self.model_name + '.log'))
        self.fh.setLevel(logging.DEBUG)
        self.fh.setFormatter(formatter)
        self.logger.addHandler(self.fh)

    def get_chunks(self):
        self.logger.debug(self.chunks_url)
        try:
            r = self.http_session.get(self.chunks_url, timeout=TIMEOUT)
            lines = r.text.splitlines()

            if len(lines) < RecordSession.MIN_CHUNKS:
                return None

            return Chunks(lines)
        except RequestException as error:
            self.logger.exception(error)
            return None

    def save_to_file(self, remote_filename, local_filename):
        self.logger.debug(remote_filename)
        file_path = os.path.join(self.output_dir, local_filename)

        ts_url = urljoin(self.base_url, remote_filename)
        try:
            session = POOL.get()
            with session.get(ts_url, stream=True, timeout=TIMEOUT) as r, open(file_path, 'wb') as fd:
                if r.status_code != 200:
                    self.logger.debug(f"Status {r.status_code}: {remote_filename}")
                    return
                for chunk in r.iter_content(chunk_size=65536):
                    fd.write(chunk)
        except BaseException as error:
            self.logger.exception(error)

    def run(self):
        global executor
        global root

        self.logger.info("Started!")
        fails = 0
        last_pos = 0

        while not self.stopped:
            chunks = self.get_chunks()
            if chunks is None:
                self.logger.info("Offline : " + self.chunks_url)
                fails += 1

                if fails > MAX_FAILS:
                    break

                time.sleep(1)
                continue
            else:
                fails = 0

            if last_pos >= chunks.cur_pos:
                time.sleep(1)
                continue

            last_pos = chunks.cur_pos
            self.logger.debug(last_pos)

            try:
                for ts in chunks.ts:
                    if ts in self.file_deq:
                        self.logger.debug("Skipped: " + ts)
                        continue

                    self.file_deq.append(ts)
                    executor.submit(self.save_to_file, ts, f'{self.file_num:020}.ts')
                    self.file_num += 1
            except BaseException as e:
                self.logger.exception(e)

            time.sleep(1)

        try:
            root.after_idle(self.main_win.set_default_state)
        except RuntimeError as e:
            self.logger.exception(e)

        self.logger.info("Exited!")
        self.fh.close()
        self.logger.removeHandler(self.fh)
        self.http_session.close()

    def stop(self):
        self.stopped = True


if __name__ == "__main__":
    if not os.path.exists(LOGS):
        os.mkdir(LOGS)
    if not os.path.exists(OUTPUT):
        os.mkdir(OUTPUT)


    my_gui = MainWindow()
    if len(sys.argv) > 4:
        w = sys.argv[1]
        h = sys.argv[2]
        x = sys.argv[3]
        y = sys.argv[4]
        root.geometry(f'+{x}+{y}')

    root.resizable(False, False)

    root.mainloop()
