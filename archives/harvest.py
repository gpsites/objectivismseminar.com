#!./.venv/bin/python

import errno
import feedparser
import json
import os
from podgen import Podcast, Media, Episode, Category, Person, NotSupportedByItunesWarning
import re
import requests
import urllib.request
import urllib.parse
import time
import warnings

sessions_filename = 'sessions.json'
rss_filename = 'rss.xml'
download_dir = "./downloads"
bucket_prefix = 'https://oapodcasts.s3.amazonaws.com/'
ipfs_prefix = 'https://cloudflare-ipfs.com/ipfs/'
feedUrl = ('https://www.freeconferencecall.com/rss/podcast' +
           '?id=2dd4f6a755aa45d0e05e72cc2367b2611992a141827eb6addeed79c5baf445fe_292812442')


def safe_name(title):
    return re.sub(r'[:/]', '_', title)


def copyfileobj(fsrc, fdst, callback, length=16*1024):
    copied = 0
    while True:
        buf = fsrc.read(length)
        if not buf:
            break
        fdst.write(buf)
        copied += len(buf)
        callback(copied)


print('>>> fetching FreeConferenceCall.com rss feed')
feed_items = feedparser.parse(feedUrl)['entries']

print('>>> loading existing sessions.json file')
session_items = json.load(open(sessions_filename))

new_items = []
for item in feed_items:
    link_info = [x for x in item['links'] if x['type'] == 'audio/mp3'][0]
    if 0 == len([session_item for session_item in session_items
                 if item['title'] == session_item['title']]):
        new_items.append({
            'title': item['title'],
            'sourcelink': link_info['href'],
            'length': int(link_info['length']),
            'description': "Please visit www.ObjectivismSeminar.com for more information.",
            'pubDate': time.strftime('%Y-%m-%dT%H:%M:%SZ', item['published_parsed'])
        })

print(f'>>> identified {len(new_items)} new session(s) by title')  # TODO: do this by pubDate?

# ensure downloads directory is in place
if not os.path.exists(download_dir):
    try:
        os.makedirs(download_dir)
    except OSError as exc:  # Guard against race condition
        if exc.errno != errno.EEXIST:
            raise

# download new items
for item in new_items:
    url = item.pop('sourcelink')
    length = item['length']
    title = item['title']

    def progress(bytes_read):
        print(f'>>> {title} -- {int(100 * bytes_read/length)}% downloaded', end='\r')

    file_path = f'{download_dir}/{safe_name(title)}.mp3'

    try:
        if os.path.getsize(file_path) == length:
            print(f'>>> {title} -- 100% downloaded')
            continue
    except FileNotFoundError:
        pass

    print(f'>>> {title} -- 0% downloaded', end='\r')
    with urllib.request.urlopen(url) as response, open(file_path, 'wb') as out_file:
        copyfileobj(response, out_file, progress)
        print(f'>>> {title} -- 100% downloaded')

# updload new items to pinata (ipfs pinning service)
for item in new_items:
    length = item['length']
    title = item['title']
    file_path = f'{download_dir}/{safe_name(title)}.mp3'
    myheaders = {
        "pinata_api_key": os.environ['PINATA_API_KEY'],
        "pinata_secret_api_key": os.environ['PINATA_SECRET_API_KEY']
    }
    myfile = {
      "file": open(file_path, 'rb')
    }

    print(f'>>> uploading {title}...', end='\r')
    response = requests.post('https://api.pinata.cloud/pinning/pinFileToIPFS',
                             files=myfile,
                             headers=myheaders)
    print(f'>>> uploaded {title}       ')
    if response.ok:
        item['CID'] = response.json()['IpfsHash']
        item['GUID'] = item["CID"]
        item['link'] = f'{ipfs_prefix}{item["CID"]}'
    else:
        raise Exception(f'upload failed for {title}', response)

# write the new sessions json file
new_session_items = new_items + session_items
with open(sessions_filename, 'w') as outfile:
    json.dump(new_session_items, outfile, indent=2)

print('>>> wrote fresh sessions.json file')

# write the new podcast rss file
p = Podcast()

p.name = "The Objectivism Seminar"
p.category = Category("Society &amp; Culture", "Philosophy")
p.language = "en-US"
p.explicit = True
p.description = ("A weekly online conference call to systematically study " +
                 "the philosophy of Objectivism via the works of prominent Rand scholars.")
p.website = "https://www.objectivismseminar.com"
p.image = "https://www.objectivismseminar.com/assets/images/atlas-square.jpg"
p.feed_url = "https://www.objectivismseminar.com/archives/rss"
p.authors = [Person("Greg Perkins", "greg@ecosmos.com")]
p.owner = p.authors[0]

warnings.simplefilter("ignore", NotSupportedByItunesWarning)
p.episodes += [Episode(title=x['title'],
                       media=Media(x['link'], type="audio/mpeg", size=x['length']),
                       id=x['GUID'],
                       publication_date=x['pubDate'],
                       summary=x['description']) for x in new_session_items]

p.rss_file(rss_filename)

print('>>> wrote fresh rss.xml file')
