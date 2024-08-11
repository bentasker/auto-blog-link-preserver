#!/usr/bin/env python3
#
# Run link preservation for all external links 
# posted on www.bentasker.co.uk
# 
#
# It's assumed that you've exported things like 
# LINKWARDEN_TOKEN and LINKWARDEN_URL into the
# environment

import sys
import requests

# Import the main script as a module
sys.path.append('../app')
import main as alr

# This is the filter that'll be used to identify which part of the page to extract links from
xpath_filter = ".//div[@itemprop='articleBody text']//div//p/a[@href]"

# Override tags and collection name
alr.LINKWARDEN_TAGS = ['SiteLinks', 'anti-link-rot', 'automated-backfill']
alr.LINKWARDEN_COLLECTION_NAME = 'Site Links'


'''
 We need a list of pages to work through
 we're going to use filesearch.bentasker.co.uk to generate this
 (see https://www.bentasker.co.uk/posts/blog/software-development/building-a-self-hosted-url-and-tags-search-engine.html)

 Start by defining a search which
 
 * matches URLs with /posts/ in
 * matches domain www.bentasker.co.uk
 * matches file extension .html
 * excludes URLs with a query string

Giving us

  /posts/ matchtype:url domain:www.bentasker.co.uk ext:html -?
'''
srch = {
    "term":"/posts/ matchtype:url domain:www.bentasker.co.uk ext:html -?",
    "type":"DOC"
    }

# Run the search
r = requests.post(
    "https://filesearch.bentasker.co.uk/search",
    json = srch
    )


# Iterate through the results
for result in r.json()['results']:
    url = result['key']
    tags = result['keywords']
    
    print(f"Processing: {url}")
    
    # Extract links from the page
    links = alr.extract_page_urls(url, xpath_filter)
    
    # Submit this page
    page_status = alr.submit_to_linkwarden(url, tags)
    if page_status == 0:
        print(f"Failed to submit {url}")
    

    # Submit each of the extracted links
    for link in links:
        retcode = alr.submit_to_linkwarden(link)
        if retcode == 0:
            print(f"Err, failed to submit {link}")
