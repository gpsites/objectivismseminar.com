import json
import requests

sessions_filename = 'sessions.json'
feedUrl = ('https://www.freeconferencecall.com/rss/podcast' +
           '?id=2dd4f6a755aa45d0e05e72cc2367b2611992a141827eb6addeed79c5baf445fe_292812442')

session_items = json.load(open(sessions_filename))

for idx, item in enumerate(session_items):
    url = item['link'].replace('https://', 'http://')
    title = item['title']

    length = int(requests.head(url).headers['Content-length'])
    item['length'] = length
    print(f'{int(idx/len(session_items)*100)}% -- {title} / length {length}')

with open('x-' + sessions_filename, 'w') as outfile:
    json.dump(session_items, outfile, indent=2)
