import requests
import argparse
import numpy as np
import json
import sys
import os
import io

from pydub import AudioSegment, effects

MEDIA_PATH = 'media'
MEDIA_STUBS_PATH = 'media-stubs'
META_PATH = 'meta.json'

FORMAT = 'mp3'

API_ROOT = 'https://xeno-canto.org/api/2/recordings'

QUERIES = [
    'lic:PD', # CC0
    'lic:BY',
    'lic:BY-SA',
]
ALLOWED_LICENSES = set([
    'creativecommons.org/publicdomain/zero/1.0/',
    'creativecommons.org/licenses/by/4.0/',
    'creativecommons.org/licenses/by-sa/4.0/',
    'creativecommons.org/licenses/by-sa/3.0/',
])

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type = int, default = None)
    args = parser.parse_args()

    if os.path.exists(MEDIA_PATH):
        media = set(os.listdir(MEDIA_PATH))
    else:
        media = set()
        os.mkdir(MEDIA_PATH)

    if os.path.exists(MEDIA_STUBS_PATH):
        for name in os.listdir(MEDIA_STUBS_PATH):
            assert name.endswith('.stub'), name
            media.add(name[:-5])
    else:
        os.mkdir(MEDIA_STUBS_PATH)

    meta = {}
    downloads = 0

    for query in QUERIES:
        page = 0
        while True:
            page += 1
            req = requests.get(f'{API_ROOT}?query={query}&page={page}')
            assert req.status_code >= 200 and req.status_code < 300, req.status_code
            res = json.loads(req.content)
            assert res['page'] == page

            for rec in res['recordings']:
                if str(rec['id']) in meta:
                    print(f'encountered duplicate entry: \'{rec["id"]}\'')
                    continue

                license = rec['lic']
                assert license.startswith('//')
                license = license[2:]
                assert license in ALLOWED_LICENSES, license

                if rec['file'] == '' and rec['file-name'] == '':
                    print(f'no media for entry {rec["id"]}')
                    continue

                media_name = f'{rec["id"]}.{FORMAT}'

                if media_name not in media:
                    media_req = requests.get(rec['file'])
                    if media_req.status_code < 200 or media_req.status_code >= 300:
                        print(f'invalid media link: {rec["file"]} (status code {media_req.status_code})')
                        continue

                    assert len(media_req.content) != 0

                    try:
                        audio = AudioSegment.from_file(io.BytesIO(media_req.content))
                        audio = effects.normalize(audio)
                        audio.export(f'{MEDIA_PATH}/{media_name}', format = FORMAT)
                    except Exception as e:
                        print(f'invalid audio encoding: {rec["file"]} -> Exception: {e}')
                        continue

                    media.add(media_name)
                    downloads += 1
                    print(f'downloaded {rec["file"]} -> {MEDIA_PATH}/{media_name}')

                    if args.limit is not None and downloads >= args.limit:
                        print('reached max download limit')
                        sys.exit(0)

                meta[str(rec['id'])] = {
                    'license': license,
                    'author': rec['rec'].strip(),

                    'species': [
                        [rec['en'].lower().strip(), rec['gen'].lower().strip(), rec['sp'].lower().strip(), rec['ssp'].lower().strip()],
                        *[['', *x.lower().split()] for x in rec['also']],
                    ],

                    'location': [rec['cnt'], rec['loc'], float(rec['lat'] or 0), float(rec['lng'] or 0)],
                    'date': rec['date'],
                    'time': rec['time'],
                    'length': (lambda t: np.sum(t * 60 ** np.array(range(len(t)))))([float(x) for x in rec['length'].split(':')[::-1]]),

                    'method': rec['method'],
                    'quality': rec['q'],
                }

            if res['numPages'] == page:
                break

    with open(META_PATH, 'w') as f:
        json.dump(meta, f)
