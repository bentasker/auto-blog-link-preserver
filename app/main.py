#!/usr/bin/env python3
#
# Fetch RSS feeds and iterate through their contents
# extracting links to the pages they reference *and* 
# external links from within the pages themselves
# 
# Submit the lot into LinkWarden and then write stats
# to InfluxDB
#

'''
Copyright (c) 2024 B Tasker

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

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


def submit_to_linkwarden(link, tags = []):
    ''' Submit a link to LinkWarden via its API
    
    Returns an integer indicating status:
    
      0 - submission failed
      1 - submission succeeded
      2 - LinkWarden reported it was a duplicate link
    
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
    
    # Add any that were supplied when calling us
    for tag in tags:
        data["tags"].append({"name":tag})
    
    headers = {
        "Authorization" : f"Bearer {LINKWARDEN_TOKEN}"
        }
    
    r = SESSION.post(
        f"{LINKWARDEN_URL}/api/v1/links", 
        headers=headers,
        json=data
        )
    
    # utilities/auto-blog-link-preserver#11
    #
    # There are two forms of success
    #
    # HTTP 200: the link was added (yay!)
    # HTTP 409: the link already existed, so LinkWarden prevented duplication
    #
    # Although 409 is a success, we want to make sure the caller knows the difference
    retcode = 0
    if r.status_code == 200:
        retcode = 1
    elif r.status_code == 409:
        retcode = 2
        
    return retcode
        
def extract_page_urls(url, xpath_filter):
    ''' Extract URLs from a page
    '''
    urls = []
    
    # Fetch the page
    r = SESSION.get(url)
    
    if "content-type" not in r.headers or "text/html" not in r.headers['content-type']:
        print(f"Skipping non HTML Page {url}")
        return urls
    
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
    duplicate_count = 0
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

        
        # Grab any tags associated with the page
        tags = []
        if hasattr(entry, "tags"):
            # Iterate over tags and add them
            [tags.append(x['term']) for x in entry.tags]
        
        # Grab outgoing links from the page
        links = extract_page_urls(entry.link, feed['XPATH_FILTER'])
        
        # Submit the link itself to linkwarden
        page_status = submit_to_linkwarden(entry.link, tags)
        # TODO: DRY this up
        if page_status == 0:
            failure_count += 1
        elif page_status == 2:
            duplicate_count += 1
        
        # Submit the outgoing links
        for link in links:
            link_count += 1
            submit_start = time.time_ns()
            retcode = submit_to_linkwarden(link)
            if retcode == 0:
                print(f"Err, failed to submit {link}")
                failure_count += 1
            elif retcode == 2:
                duplicate_count += 1
                
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
        "stats" : {
            "entries" : entry_count,
            "links" : link_count,
            "duplicates" : duplicate_count,
            "failed_submissions" : failure_count,
            "runtime": time.time_ns() - start,
        },
        "mean_submission_time": mean_submit_time 
    }


def writeStats(statslist):
    ''' Convert the stats list into line protocol and write into InfluxDB    
    '''
    
    if not INFLUXDB_URL or not INFLUXDB_BUCKET:
        # no-op
        return
    
    headers = {}
    if INFLUXDB_TOKEN:
        headers["Authorization"] = f"Token {INFLUXDB_TOKEN}"

    org = ""
    if INFLUXDB_ORG:
        org = f"&org={INFLUXDB_ORG}"

    # Construct the LP
    lp_buf = []
    ts = str(time.time_ns())
    for stat in statslist:
        lp_p1 = f"{INFLUXDB_MEASUREMENT},feed_url={stat['feed_url']}"
        
        fields = []
        for f in stat['stats']:
            fields.append(f"{f}={stat['stats'][f]}i")
        
        fields.append(f"mean_submission_time={stat['mean_submission_time']}")
        lp_p2 = ",".join(fields)
        lp_buf.append(" ".join([lp_p1, lp_p2, ts]))
    
    # Append a point to mark the completion
    lp_buf.append(f"{INFLUXDB_MEASUREMENT},level=cronjob completions=1 {time.time_ns()}")
    
    # Turn the buffer into one newline seperated text
    data = '\n'.join(lp_buf)
    
    try:
        # Submit
        r = SESSION.post(
            f"{INFLUXDB_URL}/api/v2/write?bucket={INFLUXDB_BUCKET}{org}",
            data = data,
            headers = headers,
            timeout = 10
            )
        
        if r.status_code == 204:
            print("Successfully submitted stats")
        else:
            print("Stats submission failed")
    except:
        print("Stats submission failed")


# Set config
HASH_DIR = os.getenv('HASH_DIR', 'hashes')
INFLUXDB_URL = os.getenv('INFLUXDB_URL', False)
INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', False)
INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', False)
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', False)
INFLUXDB_MEASUREMENT = os.getenv('INFLUXDB_MEASUREMENT', 'anti_link_rot')
FEEDS_FILE = os.getenv('FEEDS_FILE', 'feeds.json')
LINKWARDEN_URL = os.getenv('LINKWARDEN_URL', "https://example.com")
LINKWARDEN_TOKEN = os.getenv('LINKWARDEN_TOKEN', False)
LINKWARDEN_TAGS = os.getenv('LINKWARDEN_TAGS' , "SiteLinks").split(",")
LINKWARDEN_COLLECTION_NAME = os.getenv('LINKWARDEN_COLLECTION_NAME' , "Unorganized")
MAX_ENTRIES = int(os.getenv('MAX_ENTRIES', 0))


if __name__ == '__main__':
    
    with open(FEEDS_FILE, "r") as fh:
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
    writeStats(stats)
