import logging
import os
import subprocess
import sys
import time
from concurrent.futures.thread import ThreadPoolExecutor
from threading import Thread

import requests
from requests import RequestException
from requests.compat import urljoin

USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:68.0) Gecko/20100101 Firefox/68.0'
REFERER = 'https://sex-cams-online.net/chat-popup/'

# proxies = {"http": "http://148.217.94.54:3128"}
PROXIES = None

HEADERS = {
    'User-agent': USER_AGENT,
    'Referer': REFERER
}

MAX_FAILS = 6
PAD = 5
OUTPUT = "C:/tmp/"

logger = logging.getLogger('bonga_application')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] %(threadName)s:%(funcName)s > %(message)s')

executor = ThreadPoolExecutor(max_workers=10)


class Chunks:
    IDX_CUR_POS = 3

    def __init__(self, lines):
        self.ts = [line for line in lines if not line.startswith("#")]
        self.cur_pos = int(lines[Chunks.IDX_CUR_POS].split(':')[1])


class RecordSession(Thread):
    MIN_CHUNKS = 6

    def __init__(self, url_base, model, chunk_url, dir_output):
        super(RecordSession, self).__init__()

        self.base_url = url_base
        self.model_name = model
        self.output_dir = dir_output
        self.chunks_url = urljoin(self.base_url, chunk_url)
        self.name = 'RecordSession'
        self.stopped = False

    def get_model_name(self):
        return self.model_name

    def get_chunks(self):
        logger.debug(self.chunks_url)
        try:
            r = requests.get(self.chunks_url, headers=HEADERS, proxies=PROXIES)
            lines = r.text.splitlines()

            if len(lines) < RecordSession.MIN_CHUNKS:
                return None

            return Chunks(lines)
        except RequestException as error:
            logger.exception(error)
            return None

    def save_to_file(self, filename):
        logger.debug(filename)
        fpath = os.path.join(self.output_dir, filename)
        if os.path.exists(fpath):
            logger.debug("Skipped: " + filename)
            return

        ts_url = urljoin(self.base_url, filename)
        subprocess.run(["c:\\progs\\wget\\wget.exe", "-q", "--no-check-certificate",
                        "-O", fpath,
                        ts_url])

    def run(self):
        fails = 0
        last_pos = 0

        while not self.stopped:
            chunks = self.get_chunks()
            if chunks is None:
                logger.info("Offline : " + self.chunks_url)
                fails += 1

                if fails > MAX_FAILS:
                    return

                time.sleep(1)
                continue
            else:
                fails = 0

            if last_pos >= chunks.cur_pos:
                time.sleep(0.5)
                continue

            last_pos = chunks.cur_pos
            logger.debug(last_pos)

            try:
                for ts in chunks.ts:
                    executor.submit(self.save_to_file, ts)
            except BaseException as e:
                logger.exception(e)

            time.sleep(0.5)

    def stop(self):
        self.stopped = True


class Control(Thread):

    def __init__(self, session):
        super(Control, self).__init__()
        self.session = session
        self.daemon = True

    def run(self):
        while True:
            try:
                cmd = input()
                if cmd != 'exit':
                    print('pong')
                    continue
            except EOFError as e:
                logger.exception(e)

            print('bye')
            self.session.stop()
            return


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(1)

    base_url = sys.argv[1]
    model_name = sys.argv[2]
    chunks_url = sys.argv[3]

    output_dir = OUTPUT + model_name + '_' + str(int(time.time()))
    os.mkdir(output_dir)

    fh = logging.FileHandler(output_dir + '/' + model_name + '.log')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.info("Started!")

    record_session = RecordSession(base_url, model_name, chunks_url, output_dir)
    record_session.start()
    control = Control(record_session)
    control.start()

    record_session.join()
    logger.info("Exited!")
    print('bye')
