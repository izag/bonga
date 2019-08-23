import ctypes
import io
import subprocess
import threading
import time
import traceback
from _tkinter import TclError
from concurrent.futures.thread import ThreadPoolExecutor
from threading import Thread
from tkinter import Tk, Button, Entry, StringVar, ttk, W, E, Image, Label, Menu, DISABLED, NORMAL, END

import requests
from PIL import Image, ImageTk

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

executor = ThreadPoolExecutor(max_workers=10)


class MainWindow:

    def __init__(self, master):
        self.master = master
        menubar = Menu(self.master)
        self.history = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="History", menu=self.history)
        self.master.config(menu=menubar)

        self.session = None
        self.death_listener = None

        self.model_name = None
        self.update_title()

        level = 0

        self.image_label = Label(master)
        self.image_label.grid(row=level, column=0, columnspan=3, sticky=W + E, padx=PAD, pady=PAD)

        level += 1
        self.input_text = StringVar()
        self.entry = Entry(master, textvariable=self.input_text, width=80)
        self.entry.bind("<FocusIn>", self.entry_callback)
        self.entry.focus_set()
        self.entry.grid(row=level, column=0, columnspan=3, sticky=W + E, padx=PAD, pady=PAD)

        level += 1
        self.btn_resolutions = Button(master, text="Update info", command=self.update_model_info)
        self.btn_resolutions.grid(row=level, column=0, sticky=W + E, padx=PAD, pady=PAD)

        self.cb_resolutions = ttk.Combobox(master, state="readonly", values=[])
        self.cb_resolutions.grid(row=level, column=1, columnspan=2, sticky=W + E, padx=PAD, pady=PAD)
        self.cb_resolutions['values'] = ['1080', '720', '480', '240']

        level += 1
        self.btn_start = Button(master, text="Start", command=self.on_btn_start)
        self.btn_start.grid(row=level, column=0, sticky=W + E, padx=PAD, pady=PAD)

        self.btn_stop = Button(master, text="Stop", command=self.on_btn_stop, state=DISABLED)
        self.btn_stop.grid(row=level, column=1, sticky=W + E, padx=PAD, pady=PAD)

        self.copy_button = Button(master, text="Copy model name", command=self.copy_model_name)
        self.copy_button.grid(row=level, column=2, sticky=W + E, padx=PAD, pady=PAD)

        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

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

        self.master.title(self.model_name)
        self.session = subprocess.Popen(['python', 'session.py',
                                         self.base_url, self.model_name, "chunks.m3u8"],
                                        stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)

        self.master.configure(background='green')

        if self.death_listener is not None:
            if self.death_listener.is_alive():
                self.death_listener.raise_exception()

        self.death_listener = SessionDeathListener(self, self.session)
        self.death_listener.start()

    def on_btn_stop(self):
        self.stop()
        self.set_default_state()

    def stop(self):
        if self.session is None:
            return

        if self.death_listener is not None:
            self.death_listener.stop()
            self.death_listener = None

        try:
            self.session.communicate(b'exit', timeout=1)
        except (subprocess.TimeoutExpired, ValueError) as e:
            print(e)

        self.session = None

    def copy_model_name(self):
        self.master.clipboard_clear()
        self.master.clipboard_append(self.master.title())
        self.master.update()

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

    def entry_callback(self, event):
        self.entry.selection_range(0, END)

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

        self.master.update_idletasks()
        self.master.after(DELAY, self.load_image)

    def fetch_image(self):
        try:
            response = requests.get(self.img_url, headers=HEADERS, proxies=PROXIES)
            img = Image.open(io.BytesIO(response.content))
            self.model_image = ImageTk.PhotoImage(img)
            self.master.after_idle(self.update_image)
        except BaseException as error:
            self.master.after_idle(self.set_undefined_state)
            print("Exception URL: " + self.img_url)
            print(error)
            traceback.print_exc()

    def update_image(self):
        self.image_label.config(image=self.model_image)

    def on_close(self):
        self.stop()
        self.master.destroy()

    def set_default_state(self):
        self.session = None
        self.btn_stop.config(state=DISABLED)
        self.btn_start.config(state=NORMAL)
        self.master.configure(background='SystemButtonFace')

    def update_title(self):
        self.master.title(self.model_name or '<Undefined>')

    def set_undefined_state(self):
        self.model_image = None
        self.image_label.config(image=None)
        self.model_name = None
        self.img_url = None
        self.update_title()


class SessionDeathListener(Thread):

    def __init__(self, window, session):
        super(SessionDeathListener, self).__init__()
        self.daemon = True
        self.session = session
        self.window = window
        self.stopped = False
        self.name = 'SessionDeathListener'

    def run(self):
        if self.session is None:
            self.window.set_default_state()
            return

        try:
            while not self.stopped:
                self.session.stdin.write(b'ping\n')
                self.session.stdin.flush()
                answer = self.session.stdout.readline()

                if answer == 'bye':
                    self.window.set_default_state()
                    return

                time.sleep(1)
        except BaseException as e:
            print(e)
            traceback.print_exc()
            self.window.set_default_state()

    def raise_exception(self):
        thread_id = threading.get_ident()
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id,
                                                         ctypes.py_object(SystemExit))
        if res > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
            print(self.name + '> Exception raise failure')

    def stop(self):
        self.stopped = True


if __name__ == "__main__":
    root = Tk()
    root.resizable(False, False)
    my_gui = MainWindow(root)
    root.mainloop()
