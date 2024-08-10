#!/usr/bin/env python3
import feedparser
import json
import hashlib
import os
import requests
import time
from lxml import etree


def get_linkwarden_collection(name):
    ''' Get details of a linkwarden collection
    '''
    headers = {
            "Authorization" : f"Bearer {LINKWARDEN_TOKEN}"
            }
    
    r = SESSION.get(
            f"{LINKWARDEN_URL}/api/v1/collections", 
            headers=headers
        )    
    
    # Iterate through the response
    j = r.json()
    for c in j['response']:
        if name == c['name']:
            print("Found collection")
            return {
                "id" : c['id'],
                "name" : c['name'],
                "ownerId" : c['ownerId']
                }
    
    # Otherwise, there was no match, return False
    return False


def submit_to_linkwarden(link):
    ''' Submit a link to LinkWarden via its API
    '''
    
    if not LINKWARDEN_COLLECTION[0]:
        # We haven't tried to get collection details yet
        LINKWARDEN_COLLECTION[0] = True
        LINKWARDEN_COLLECTION[1] = get_linkwarden_collection(LINKWARDEN_COLLECTION_NAME)
    
    collection = {}
    if LINKWARDEN_COLLECTION[1]:
        collection = LINKWARDEN_COLLECTION[1]
    
    # Build the data to submit
    data =  {
        "name" : "",
        "url": link,
        "description" : "",
        "type" : "url",
        "tags": [],
        "preview":"",
        "image":"",
        "pdf":"",
        "readable":"",
        "monolith":"",
        "textContent":"",
        "collection": LINKWARDEN_COLLECTION[1]
    }        
    
    for tag in LINKWARDEN_TAGS:
        data["tags"].append({"name":tag})
    
    headers = {
        "Authorization" : f"Bearer {LINKWARDEN_TOKEN}"
        }
    
    r = SESSION.post(
        f"{LINKWARDEN_URL}/api/v1/links", 
        headers=headers,
        json=data
        )
    
    return r.status_code == 200

def extract_page_urls(url, xpath_filter):
    ''' Extract URLs from a page
    '''
    
    # The first is the easiest - the url to the page itself
    urls = [url]
    
    # Fetch the page
    r = SESSION.get(url)
    
    # Parse the page - be permissive about syntax errors etc 
    parser = etree.XMLParser(recover=True)
    root = etree.fromstring(r.text, parser=parser)
    

    if not xpath_filter:
        xpath_filter = ".//a[@href]"
    
    links = root.findall(xpath_filter)

    for link in links:
        dst = link.attrib["href"]
        # Skip relative links
        if not dst.startswith("http://") and not dst.startswith("https://"):
            continue
        
        # Strip any url fragment
        dst_s = dst.split("#")
        
        if dst_s[0] not in urls:
            urls.append(dst_s[0])

    return urls


def check_if_link_seen(linkhash, storedhash, feed):
    ''' Check whether the current hashed URL has previously been seen
    Return: boolean
    '''
    hashfile = f"{feed['HASH_DIR']}/{linkhash}"
    return os.path.exists(hashfile)


def write_hash_to_storage(linkhash, feed, hashtracker, firsthash):
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
    
    start = time.time_ns()
    storedhash = False
    hashtracker = False
    entry_count = 0
    link_count = 0
    failure_count = 0
    submit_times = []
    
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
        
        if check_if_link_seen(linkhash, storedhash, feed):
            print("Reached last seen entry")
            break

        # Keep a record of the hash for the first item in the feed
        # misc/Python_mastodon_rss_bot#1
        if not firsthash:
            firsthash = linkhash

        # Extract links
        print(f"seen {entry.link}")
        links = extract_page_urls(entry.link, feed['XPATH_FILTER'])
        
        for link in links:
            link_count += 1
            submit_start = time.time_ns()
            if not submit_to_linkwarden(link):
                print(f"Err, failed to submit {link}")
                failure_count += 1
            submit_times.append(time.time_ns() - submit_start)
        
        write_hash_to_storage(linkhash, feed, hashtracker, firsthash)

        # Increase the counter
        entry_count += 1
        

    if hashtracker:
        hashtracker.close()

    mean_submit_time = -100
    if len(submit_times) > 0:
        mean_submit_time = sum(submit_times) / len(submit_times)
        
    return {
        "feed_url" : feed['FEED_URL'],
        "entries" : entry_count,
        "links" : link_count,
        "failed_submissions" : failure_count,
        "runtime": time.time_ns() - start,
        "mean_submission_time": mean_submit_time 
    }


# Set config
HASH_DIR = os.getenv('HASH_DIR', 'hashes')
LINKWARDEN_URL = os.getenv('LINKWARDEN_URL', "https://example.com")
LINKWARDEN_TOKEN = os.getenv('LINKWARDEN_TOKEN', False)
LINKWARDEN_TAGS = os.getenv('LINKWARDEN_TAGS' , "SiteLinks").split(",")
LINKWARDEN_COLLECTION_NAME = os.getenv('LINKWARDEN_COLLECTION_NAME' , "Unorganized")
MAX_ENTRIES = int(os.getenv('MAX_ENTRIES', 0))

with open("feeds.json", "r") as fh:
    FEEDS = json.load(fh)

# We want to be able to use keep-alive if we're posting multiple things
SESSION = requests.session()

# This is used as a cache and will be updated later
LINKWARDEN_COLLECTION = [False, False]

# Iterate through feeds
stats = []
for feed in FEEDS:
    # Calculate the hashdir if not already set
    if "HASH_DIR" not in feed:
        feed['HASH_DIR'] = f"{HASH_DIR}/{feed['FEED_URL'].replace('/','-').replace('.','-')}.urls"

    if "XPATH_FILTER" not in feed:
        feed['XPATH_FILTER'] = False

    if not os.path.exists(feed['HASH_DIR']):
        os.makedirs(feed['HASH_DIR'])
    
    stats.append(process_feed(feed))

print(stats)
