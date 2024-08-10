#!/usr/bin/env python3
import feedparser
import json
import hashlib
import os
import requests
import time


def build_toot(entry):
    ''' Take the entry dict and build a toot
    '''
    
    skip_tags = SKIP_TAGS
    skip_tags.append("blog")
    skip_tags.append("documentation")
    skip_tags.append(CW_TAG)
    
    toot_str = ''
    
    if "blog" in entry['tags']:
        toot_str += "New #Blog: "
    elif "documentation" in entry['tags']:
        toot_str += "New #Documentation: "
    
    toot_str += f"{entry['title']}\n"
    
    if entry['author']:
        toot_str += f"Author: {entry['author']}\n"
    
    toot_str += f"\n\n{entry['link']}\n\n"
    
    # Tags to hashtags
    if len(entry['tags']) > 0:
        for tag in entry['tags']:
            if tag in skip_tags:
                # Skip the tag
                continue
            toot_str += f'#{tag.replace(" ", "")} '
        
    return toot_str


def send_toot(en):
    ''' Turn the dict into toot text
    
    and send the toot
    '''
    toot_txt = build_toot(en)
    #print(toot_txt)
    
    headers = {
        "Authorization" : f"Bearer {MASTODON_TOKEN}"
        }
    
    data = {
        'status': toot_txt,
        'visibility': MASTODON_VISIBILITY
        }
    
    if en['cw']:
        data['spoiler_text'] = en['title']
    
    if DRY_RUN == "Y":
        print("------")
        print(data['status'])
        print(data)
        print("------")
        return True
    
    try:
        resp = SESSION.post(
            f"{MASTODON_URL.strip('/')}/api/v1/statuses",
            data=data,
            headers=headers
        )
        
        if resp.status_code == 200:
            return True
        else:
            print(f"Failed to post {en['link']}")
            print(resp.status_code)
            return False
    except:
        print(f"Urg, exception {en['link']}")
        return False
    


def check_if_link_seen(mode, linkhash, storedhash, feed):
    ''' Check whether the current hashed URL has previously been seen
    Return: boolean
    '''
    hashfile = f"{feed['HASH_DIR']}/{linkhash}"
    return os.path.exists(hashfile)


def write_hash_to_storage(mode, linkhash, feed, hashtracker, firsthash):
    ''' Write the hash to statefile(s)
    '''

    # We use per-url tracking, so switch out the tracker file handle
    # and set firsthash to be the same as the linkhash
    #
    # TODO: Refactor away the need to do this, we don't do persite tracking
    # anymore
    #
    hashfile = f"{feed['HASH_DIR']}/{linkhash}"
    hashtracker = open(hashfile,'w')
    firsthash = linkhash
        
    hashtracker.seek(0)
    hashtracker.truncate()
    hashtracker.write(firsthash)
    return
    
    
def process_feed(feed):
    ''' Process the RSS feed and generate a toot for any entry we haven't yet seen
    '''
    
    storedhash = False
    hashtracker = False
    entry_count = 0
    
    # This will be overridden as we iterate through
    firsthash = False

    # Load the feed
    d = feedparser.parse(feed['FEED_URL'])

    # Iterate over entries
    for entry in d.entries:
        
        
        # Have we hit the MAX_ENTRIES limit
        if MAX_ENTRIES > 0 and entry_count >= MAX_ENTRIES:
            print(f"Reached MAX_ENTRIES ({MAX_ENTRIES})")
            break
        
        # compare a checksum of the URL to the stored one
        # this is used to prevent us re-sending old items
        linkhash = hashlib.sha1(entry.link.encode('utf-8')).hexdigest()
        print('{}: {}'.format(entry.link,linkhash))
        
        if check_if_link_seen(TRACKING_MODE, linkhash, storedhash, feed):
            print("Reached last seen entry")
            break
                   
        en = {}
        en['title'] = entry.title
        en['link'] = entry.link
        en['author'] = False       
        en['tags'] = []
        
        if hasattr(entry, "tags"):
            # Iterate over tags and add them
            [en['tags'].append(x['term']) for x in entry.tags]
        
        en['cw'] = CW_TAG in en['tags']
        
        if INCLUDE_AUTHOR == "True" and hasattr(entry, "author"):
            en['author'] = entry.author
        
        #print(en)

        # Keep a record of the hash for the first item in the feed
        # misc/Python_mastodon_rss_bot#1
        if not firsthash:
            firsthash = linkhash
            
        # Send the toot
        if send_toot(en):
            # If that worked, write hash to disk to prevent re-sending
            write_hash_to_storage(TRACKING_MODE, linkhash, feed, hashtracker, firsthash)
            time.sleep(1)
        
        # Increase the counter
        entry_count += 1
        

    if hashtracker:
        hashtracker.close()



# Set config
HASH_DIR = os.getenv('HASH_DIR', 'hashes')
ARCHIVE_BOX_URL = os.getenv('ARCHIVEBOX_URL', "https://example.com")
ARCHIVE_BOX_USER = os.getenv('ARCHIVEBOX_USER', "ab")
ARCHIVE_BOX_USER = os.getenv('ARCHIVEBOX_PASSWORD', False)
DRY_RUN = os.getenv('DRY_RUN', "N").upper()
TRACKING_MODE = os.getenv('TRACKING_MODE', "LASTPAGE").upper()
MAX_ENTRIES = int(os.getenv('MAX_ENTRIES', 0))


with open("feeds.json", "r") as fh:
    FEEDS = json.load(fh)

# We want to be able to use keep-alive if we're posting multiple things
SESSION = requests.session()

# Iterate through feeds
for feed in FEEDS:
    # Calculate the hashdir if not already set
    if "HASH_DIR" not in feed:
        feed['HASH_DIR'] = f"{HASH_DIR}/{feed['FEED_URL'].replace("/","-").replace(".","-")}.urls"

    if not os.path.exists(feed['HASH_DIR']):
        os.makedirs(feed['HASH_DIR'])
    
    process_feed(feed)
