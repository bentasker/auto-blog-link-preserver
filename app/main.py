#!/usr/bin/env python3
import feedparser
import json
import hashlib
import os
import requests
import time
from lxml import etree


def archivebox_scrape_add_csrf():
    ''' Call the add page and extract the CSRF token
    '''
    r = SESSION.get(f"{ARCHIVE_BOX_URL}/add/")
    parser = etree.XMLParser(recover=True)
    root = etree.fromstring(r.text, parser=parser)
    
    form_item = root.find(".//input[@name='csrfmiddlewaretoken']")
    return form_item.attrib["value"]


def archivebox_scrap_add_url(url):
    ''' Submit a URL to archivebox
    '''
    
    data = {
        "csrfmiddlewaretoken": archivebox_scrape_add_csrf(),
        "url": url,
        "parser": "auto",
        "tag": "",
        "depth": 0
        }
    
    try:
        r = SESSION.post(
            f"{ARCHIVE_BOX_URL}/add/", 
            data=data, 
            timeout=REQUESTS_TIMEOUT,
            allow_redirects=False
            )
        return r.status_code == 200
    except requests.exceptions.ReadTimeout:
        # We hit the expected timeout
        #
        # When submitting through the Web UI, the code 
        # doesn't wait for a response - because that seems
        # to take forever (utilities/auto-blog-link-preserver#6)
        #
        # So, we should also treat a lack of response as success
        #
        # TODO: Figure out if there's a way we can validate success
        return True


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
        
        # We're not doing multi-submission for now
        url_list = "\r\n".join(links)
        
        if not archivebox_scrap_add_url(url_list):
            print(f"Err, failed to submit links for {entry.link}")
            # Let archivebox catch up
            failure_count += 1
            time.sleep(20)
            continue
        
        # Give archivebox a second to catch up
        time.sleep(10)
                
        write_hash_to_storage(linkhash, feed, hashtracker, firsthash)

        # Increase the counter
        entry_count += 1
        

    if hashtracker:
        hashtracker.close()

    return {
        "feed_url" : feed['FEED_URL'],
        "entries" : entry_count,
        "links" : link_count,
        "failed_submissions" : failure_count,
        "runtime": time.time_ns() - start
        }


# Set config
HASH_DIR = os.getenv('HASH_DIR', 'hashes')
ARCHIVE_BOX_URL = os.getenv('ARCHIVEBOX_URL', "https://example.com")

# This isn't currently used, see utilities/auto-blog-link-preserver#5
ARCHIVE_BOX_TOKEN = os.getenv('ARCHIVEBOX_TOKEN', False)

REQUESTS_TIMEOUT = int(os.getenv('REQUESTS_TIMEOUT', 2))

DRY_RUN = os.getenv('DRY_RUN', "N").upper()
MAX_ENTRIES = int(os.getenv('MAX_ENTRIES', 0))


with open("feeds.json", "r") as fh:
    FEEDS = json.load(fh)

# We want to be able to use keep-alive if we're posting multiple things
SESSION = requests.session()

'''
url = "https://www.bentasker.co.uk/posts/blog/house-stuff/ecover-dishwasher-tablets-left-white-grit-over-everything.html"
r = archivebox_scrap_add_url(url)
print(r.status_code)
'''


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
