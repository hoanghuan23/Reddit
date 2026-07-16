from app.services.reddit_client import RedditClient


def test_build_listing_urls_for_all_source_types():
    client = RedditClient(cookie_service=None)

    assert client.build_listing_urls("subreddit", "python")[0] == "https://www.reddit.com/r/python/new.json"
    assert client.build_listing_urls("keyword", "memory leak")[0] == "https://www.reddit.com/search.json?q=memory%20leak&sort=new"
    assert client.build_listing_urls("user", "spez")[0] == "https://www.reddit.com/user/spez/submitted.json?sort=new"
    assert client.build_listing_urls("latest", "all")[0] == "https://www.reddit.com/r/all/new.json"
