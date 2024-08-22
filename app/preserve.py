#!/usr/bin/env python3
#
# A small CLI to fetch and preserve
# a link and any others that it links
# out to.
#
# It is assumed the environment variables are
# set as if you were running the main application
#
#

'''
Copyright (c) 2024 B Tasker

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

import os
import sys
import requests

# Import the main script as a module
sys.path.append(os.path.dirname(__file__))
import main as alr

url = sys.argv[1]
submit_statuses = {}

for i in alr.SUBMIT_STATUS:
    submit_statuses[i] = 0

# TODO: allow a custom xpath filter to be applied
# we should also provide a way to reference one that might
# be recorded against a feed url
links = alr.extract_page_urls(url, False)

# TODO: do we want to accept tags on the commandline?
retcode = alr.submit_to_linkwarden(url, [])
submit_statuses[alr.SUBMIT_STATUS[retcode]] += 1
print(f"Linkwarden submission reported: {alr.SUBMIT_STATUS[retcode]}")


# Iterate through the links
print("Processing links")
link_count = 1
for link in links:
    link_count += 1
    retcode = alr.submit_to_linkwarden(link)
    submit_statuses[alr.SUBMIT_STATUS[retcode]] += 1
    
print(f"Submitted {link_count} links")
for i in submit_statuses:
    print(f"  {i}: {submit_statuses[i]}")
    
