#!./.venv/bin/python

import errno
import feedparser
import json
import os
from podgen import Podcast, Media, Episode, Category, Person
import re
import requests
import urllib.request
import urllib.parse
import time

default_description = "Please visit www.ObjectivismSeminar.com for more information."
sessions_filename = 'sessions.json'
rss_filename = 'rss.xml'
download_dir = "./downloads"
bucket_prefix = 'https://oapodcasts.s3.amazonaws.com/'
# ipfs_prefix = 'https://cloudflare-ipfs.com/ipfs/'
ipfs_prefix = 'https://gateway.pinata.cloud/ipfs/'
ipfs_suffix = '/audio.mp3'
feedUrl = ('https://www.freeconferencecall.com/rss/podcast' +
           '?id=2dd4f6a755aa45d0e05e72cc2367b2611992a141827eb6addeed79c5baf445fe_292812442')


def safe_name(title):
    return re.sub(r'[:/]', '_', title)


def safe_pinata_path(title):
    return re.sub(r'[:/.]', '_', title)


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
    link_info = next((x for x in item['links'] if x['type'] == 'audio/mp3'), None)
    if not next((x for x in session_items if item['title'] == x['title']), None):
        new_items.append({
            'title': item['title'],
            'sourcelink': link_info['href'],
            'length': int(link_info['length']),
            'description': default_description,
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
        # Using the title as an IPFS directory containing audio.mp3 because
        # stupid iTunes just HAS to see an .mp3 at the end of a URL.
        "file": (f'{safe_pinata_path(title)}{ipfs_suffix}', open(file_path, 'rb'))
    }

    print(f'>>> uploading {title}...', end='\r')
    response = requests.post('https://api.pinata.cloud/pinning/pinFileToIPFS',
                             files=myfile,
                             headers=myheaders)
    print(f'>>> uploaded {title}       ')
    if not response.ok:
        raise Exception(f'upload failed for {title}', response.text)

    cid = response.json()['IpfsHash']
    item['CID'] = cid
    item['GUID'] = cid
    if next((x for x in session_items if x['CID'] == cid), None):
        print(f'WARNING: duplicate CID {cid} for new item: {title}')

# write the new sessions json file
updated_session_items = new_items + session_items

for item in updated_session_items:
    item['link'] = f'{ipfs_prefix}{item["CID"]}{ipfs_suffix}'

with open(sessions_filename, 'w') as outfile:
    json.dump(updated_session_items, outfile, indent=2)

print('>>> wrote fresh sessions.json file')

# write the new rss file
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
p.authors = [Person("Greg Perkins, Host", "greg@objectivismseminar.com")]
p.owner = Person("Greg Perkins", "greg@ecosmos.com")

p.episodes += [Episode(title=x['title'],
                       media=Media(x['link'], type="audio/mpeg", size=x['length']),
                       id=x['GUID'],
                       publication_date=x['pubDate'],
                       summary=x['description']) for x in updated_session_items]

p.rss_file(rss_filename)

print('>>> wrote fresh rss.xml file')
