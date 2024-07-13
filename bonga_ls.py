import datetime
import json
import os
import requests
from livestreamer import Livestreamer

MODEL_NAME = 'Taanni'  # enter model name


def get_data(model):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.101 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest',
    }
    data = [('method', 'getRoomData'), ('args[]', model)]
    r = requests.post('https://bongacams.com/tools/amf.php', headers=headers, data=data)
    return json.loads(r.text)


def stream(video_server_url, model):
    session = Livestreamer()
    session.set_option('http-headers', 'referer=https://bongacams.com/%s' % model)

    url = 'hlsvariant://https:%s/hls/stream_%s/playlist.m3u8' % (video_server_url, model)

    streams = session.streams(url)
    best_stream = streams['best']
    fd = best_stream.open()

    now = datetime.datetime.now()
    file_path = '%s/%s.mp4' % (model, model + now.strftime('%Y-%m-%d-%H-%M'))
    print(' - Start record stream')
    if not os.path.exists(model):
        os.makedirs(model)
    with open(file_path, 'wb') as f:
        while True:
            try:
                chunk = fd.read(1024)
                f.write(chunk)
            except:
                print(' - Error write record into file')
                f.close()
                return


if __name__ == '__main__':
    data = get_data(MODEL_NAME)
    if 'videoServerUrl' in data['localData']:
        stream(data['localData']['videoServerUrl'], MODEL_NAME)
    else:
        print(' - This model just now offline')
