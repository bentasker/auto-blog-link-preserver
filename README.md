# Auto Blog Link Preserver

This script is intended as a way to help mitigate the risk of [link rot](https://en.wikipedia.org/wiki/Link_rot) in blogs.

It consumes a site's RSS feed in order to fetch posts, extract outgoing links from them and submit all into [LinkWarden](https://github.com/linkwarden/linkwarden)


Project management can be found [in my github mirror](https://projects.bentasker.co.uk/gils_projects/project/utilities/auto-blog-link-preserver.html).

----

## Environment Vars

Most configuration is performed using environment variables

### General Config 

* `HASH_DIR`: the directory to store hashes to track which RSS items have been seen (default `./hashes`)
* `FEEDS_FILE`: the location of the [feeds config file](#feeds_config_file) (default `./feeds.json`)
* `MAX_ENTRIES`: the maximum number of feed items to process in any invocation (default is 0, unlimited)

### Link Warden Config

You'll need to log into your Linkwarden account and generate an access token.

Then provide the following

* `LINKWARDEN_URL`: the URL for your instance (e.g. `https://linkwarden.example.com`)
* `LINKWARDEN_TOKEN`: The authentication token to use
* `LINKWARDEN_COLLECTION_NAME`: The name of the collection to put links into (default is `Unorganized`)
* `LINKWARDEN_TAGS`: a comma separated list of tags to attach to links (default is `SiteLinks`)

Note: if the provided collection name is not valid, links will be put into the `Unorganized` collection.


### InfluxDB Config

The script can optionally write runtime stats to [InfluxDB](https://github.com/influxdata/influxdb) to allow monitoring of executions.

* `INFLUXDB_URL`: the URL to InfluxDB (e.g. `http://influxdb.example.com:8086`)
* `INFLUXDB_TOKEN`: (optional) the token to provide to InfluxDB (for 1.8, set this in the format `user:password`)
* `INFLUXDB_BUCKET`: The bucket to write stats into
* `INFLUXDB_MEASUREMENT`: The measurement name to use (default is `anti_link_rot`)

----

<a name="feeds_config_file"></a>

### Feeds Config

The feeds config file is a small JSON file defining information about feeds and how to parse the pages that they reference:

```json
[ 
    {
        "FEED_URL" : "https://www.bentasker.co.uk/rss.xml",
        "XPATH_FILTER" : ".//div[@itemprop='articleBody text']//div//p/a[@href]"
    }
]
```

The `XPATH_FILTER` option is optional, but **highly** recommended - it's used to constrain where in linked pages links are collected from (so that you're not constantly [collecting social media share links etc](https://projects.bentasker.co.uk/gils_projects/issue/utilities/auto-blog-link-preserver/4.html#comment7654)).


----

### Running

The simplest way to run is with Docker:
```sh
docker run \
--rm \
-v "$PWD/feeds.json":/app/feeds.json \
-v "$PWD/hashes":/hashdir \
-e LINKWARDEN_URL="https://linkwarden.83n.uk" \
-e LINKWARDEN_TOKEN="$LINKWARDEN_TOKEN" \
-e LINKWARDEN_TAGS="SiteLinks,anti-link-rot" \
-e LINKWARDEN_COLLECTION_NAME="Site Links" \
-e INFLUXDB_URL=http://192.168.3.84:8086 \
-e INFLUXDB_BUCKET=testing_db \
ghcr.io/bentasker/auto-blog-link-preserver:0.1

```

There's also [an example](examples/anti-link-rot.yml) of creating a K8S cronjob (see [#13](https://projects.bentasker.co.uk/gils_projects/issue/utilities/auto-blog-link-preserver/13.html) for details on creating the secrets).

----

## Use as a module

Although not the primary use-case, it's also possible to import the script as module in order to use it's functionality for a list of URLs **not** sourced from a RSS feed.

[`examples/crawl_and_preserve.py`](examples/crawl_and_preserve.py) is an example of this. It [searches for](https://www.bentasker.co.uk/posts/blog/software-development/building-a-self-hosted-url-and-tags-search-engine.html) all posts on `www.bentasker.co.uk` and then iterates through [the results](https://filesearch.bentasker.co.uk/?q=%2Fposts%2F+%2Fpages%2F+matchtype%3Aurl+mode%3Aor+domain%3Awww.bentasker.co.uk+ext%3Ahtml+-%3F&t=) preserving each post and any URL linked out to from within those posts.

The functions that you need to be aware of are 

* `extract_page_urls(url, xpath_filter)`: consume a HTML page and extract any links found under the path specified in `xpath_filter`
* `submit_to_linkwarden(url, tags)`: submit a URL to linkwarden, attaching any tags included in the list `tags`



----

### Copyright

Copyright (c) 2024 [Ben Tasker](https://www.bentasker.co.uk)

Released under [MIT License](https://www.bentasker.co.uk/pages/licenses/mit-license.html)



