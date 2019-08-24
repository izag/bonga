import io
import logging
import os
import subprocess
import time
import traceback
from _tkinter import TclError
from concurrent.futures.thread import ThreadPoolExecutor
from threading import Thread
from tkinter import Tk, Button, Entry, StringVar, ttk, W, E, Image, Label, Menu, DISABLED, NORMAL, END

import requests
from PIL import Image, ImageTk
from requests import RequestException
from requests.compat import urljoin

USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:68.0) Gecko/20100101 Firefox/68.0'
REFERER = 'https://sex-cams-online.net/chat-popup/'

# proxies = {
#     "http": "http://2.36.241.131:8118",
#     "https": "https://2.36.241.131:8118"
# }
PROXIES = None

HEADERS = {
    'User-agent': USER_AGENT,
    'Referer': REFERER
}

DELAY = 2000
PAD = 5
MAX_FAILS = 6
OUTPUT = "C:/tmp/"

executor = ThreadPoolExecutor(max_workers=20)

root = Tk()


class MainWindow:

    def __init__(self):
        menu_bar = Menu(root)
        self.history = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="History", menu=self.history)
        root.config(menu=menu_bar)

        self.session = None

        self.model_name = None
        self.update_title()

        level = 0

        self.image_label = Label(root)
        self.image_label.grid(row=level, column=0, columnspan=3, sticky=W + E, padx=PAD, pady=PAD)

        level += 1
        self.input_text = StringVar()
        self.entry = Entry(root, textvariable=self.input_text, width=80)
        self.entry.bind("<FocusIn>", self.focus_callback)
        self.entry.bind('<Return>', self.enter_callback)
        self.entry.focus_set()
        self.entry.grid(row=level, column=0, columnspan=3, sticky=W + E, padx=PAD, pady=PAD)

        level += 1
        self.btn_resolutions = Button(root, text="Update info", command=self.update_model_info)
        self.btn_resolutions.grid(row=level, column=0, sticky=W + E, padx=PAD, pady=PAD)

        self.cb_resolutions = ttk.Combobox(root, state="readonly", values=[])
        self.cb_resolutions.grid(row=level, column=1, columnspan=2, sticky=W + E, padx=PAD, pady=PAD)
        self.cb_resolutions['values'] = ['1080', '720', '480', '240']

        level += 1
        self.btn_start = Button(root, text="Start", command=self.on_btn_start)
        self.btn_start.grid(row=level, column=0, sticky=W + E, padx=PAD, pady=PAD)

        self.btn_stop = Button(root, text="Stop", command=self.on_btn_stop, state=DISABLED)
        self.btn_stop.grid(row=level, column=1, sticky=W + E, padx=PAD, pady=PAD)

        self.copy_button = Button(root, text="Copy model name", command=self.copy_model_name)
        self.copy_button.grid(row=level, column=2, sticky=W + E, padx=PAD, pady=PAD)

        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.play_list_url = None
        self.base_url = None
        self.model_image = None
        self.img_url = None

        self.load_image()

    def on_btn_start(self):
        self.btn_stop.config(state=NORMAL)
        self.btn_start.config(state=DISABLED)

        self.stop()

        success = self.update_model_info()
        if not success:
            self.set_default_state()
            return

        idx = self.cb_resolutions.current()

        items_count = len(self.cb_resolutions['value'])
        if items_count == 0:
            return

        if items_count <= idx or idx < 0:
            idx = 0

        self.cb_resolutions.current(idx)

        root.title(self.model_name)
        self.session = RecordSession(self, self.base_url, self.model_name, "chunks.m3u8")
        self.session.start()

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
        root.clipboard_clear()
        root.clipboard_append(root.title())
        root.update()

    def update_model_info(self):
        self.set_undefined_state()
        input_url = self.input_text.get().strip()

        if len(input_url) == 0:
            return False

        self.base_url = None
        if input_url.startswith('https://ded'):
            public_pos = input_url.rfind('public')
            self.base_url = input_url[: public_pos + 7]

            stream_pos = self.base_url.find('stream_')
            slash_pos = self.base_url.find('/', stream_pos)

            self.model_name = self.base_url[stream_pos + 7: slash_pos]
        elif input_url.startswith('http'):
            slash_pos = input_url[: -1].rfind('/')
            self.model_name = input_url[slash_pos + 1: -1] if input_url.endswith('/') else input_url[slash_pos + 1:]
        else:
            self.model_name = input_url

        if self.base_url is None:
            info = self.get_model_info()
            print(info)
            if 'localData' not in info:
                self.set_undefined_state()
                return False

            server_url = info['localData']['videoServerUrl']
            self.base_url = f"https:{server_url}/hls/stream_{self.model_name}/public/stream_{self.model_name}/"

        self.get_image_url()
        self.add_to_history()
        self.update_title()

        return True

    def add_to_history(self):
        try:
            self.history.index(self.model_name)
        except TclError:
            arg = f'{self.model_name}'
            self.history.insert_command(0,
                                        label=self.model_name,
                                        command=lambda: self.load_from_history(arg))

    def load_from_history(self, model):
        self.input_text.set(model)
        self.update_model_info()

    def focus_callback(self, event):
        self.entry.selection_range(0, END)

    def enter_callback(self, event):
        self.update_model_info()

    def get_image_url(self):
        edge_pos = self.base_url.find('-edge')
        point_pos = self.base_url.find('.', edge_pos)
        vsid = self.base_url[edge_pos + 5: point_pos]
        self.img_url = f"https://mobile-edge{vsid}.bcrncdn.com/stream_{self.model_name}.jpg"

    def get_model_info(self):
        post_fields = {
            'method': 'getRoomData',
            'args[]': [self.model_name, False]
        }

        headers = HEADERS.copy()
        headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        headers['X-Requested-With'] = 'XMLHttpRequest'

        response = requests.post("https://sex-cams-online.net/tools/amf.php",
                                 data=post_fields,
                                 headers=headers,
                                 proxies=PROXIES)

        return response.json()

    def load_image(self):
        if self.img_url is not None:
            executor.submit(self.fetch_image)

        root.update_idletasks()
        root.after(DELAY, self.load_image)

    def fetch_image(self):
        try:
            response = requests.get(self.img_url, headers=HEADERS, proxies=PROXIES)
            img = Image.open(io.BytesIO(response.content))
            root.after_idle(self.update_image, img)
        except BaseException as error:
            root.after_idle(self.set_undefined_state)
            print("Exception URL: " + self.img_url)
            print(error)
            traceback.print_exc()

    def update_image(self, img):
        self.model_image = ImageTk.PhotoImage(img)
        self.image_label.config(image=self.model_image)

    def on_close(self):
        self.stop()
        root.update_idletasks()
        root.destroy()

    def set_default_state(self):
        self.session = None
        self.btn_stop.config(state=DISABLED)
        self.btn_start.config(state=NORMAL)
        root.configure(background='SystemButtonFace')

    def update_title(self):
        root.title(self.model_name or '<Undefined>')

    def set_undefined_state(self):
        self.model_image = None
        self.image_label.config(image=None)
        self.model_name = None
        self.img_url = None
        self.update_title()


class Chunks:
    IDX_CUR_POS = 3

    def __init__(self, lines):
        self.ts = [line for line in lines if not line.startswith("#")]
        self.cur_pos = int(lines[Chunks.IDX_CUR_POS].split(':')[1])


class RecordSession(Thread):
    MIN_CHUNKS = 6

    def __init__(self, main_win, url_base, model, chunk_url):
        super(RecordSession, self).__init__()

        self.main_win = main_win
        self.base_url = url_base
        self.model_name = model
        self.output_dir = os.path.join(OUTPUT, self.model_name + '_' + str(int(time.time())))
        os.mkdir(self.output_dir)

        self.chunks_url = urljoin(self.base_url, chunk_url)
        self.name = 'RecordSession'
        self.stopped = False

        self.logger = logging.getLogger('bonga_application')
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[%(asctime)s] %(threadName)s:%(funcName)s > %(message)s')

        self.fh = logging.FileHandler(os.path.join(self.output_dir, self.model_name + '.log'))
        self.fh.setLevel(logging.DEBUG)
        self.fh.setFormatter(formatter)
        self.logger.addHandler(self.fh)

    def get_model_name(self):
        return self.model_name

    def get_chunks(self):
        self.logger.debug(self.chunks_url)
        try:
            r = requests.get(self.chunks_url, headers=HEADERS, proxies=PROXIES)
            lines = r.text.splitlines()

            if len(lines) < RecordSession.MIN_CHUNKS:
                return None

            return Chunks(lines)
        except RequestException as error:
            self.logger.exception(error)
            return None

    def save_to_file(self, filename):
        self.logger.debug(filename)
        fpath = os.path.join(self.output_dir, filename)
        if os.path.exists(fpath):
            self.logger.debug("Skipped: " + filename)
            return

        ts_url = urljoin(self.base_url, filename)
        subprocess.run(["c:\\progs\\wget\\wget.exe", "-q", "--no-check-certificate",
                        "-O", fpath,
                        ts_url])

    def run(self):
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
                time.sleep(0.5)
                continue

            last_pos = chunks.cur_pos
            self.logger.debug(last_pos)

            try:
                for ts in chunks.ts:
                    executor.submit(self.save_to_file, ts)
            except BaseException as e:
                self.logger.exception(e)

            time.sleep(0.5)

        root.after_idle(self.main_win.set_default_state)
        self.logger.info("Exited!")
        self.fh.close()
        self.logger.removeHandler(self.fh)

    def stop(self):
        self.stopped = True


if __name__ == "__main__":
    root.resizable(False, False)
    my_gui = MainWindow()
    root.mainloop()