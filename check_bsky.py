import os
import requests

ACTOR = "489wiki.bsky.social"
FEED_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
STATE_FILE = "last_seen.txt"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def uri_to_url(uri: str, handle: str) -> str:
    rkey = uri.rstrip("/").split("/")[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def post_to_discord(text: str, url: str, author_name: str, handle: str) -> None:
    payload = {
        "embeds": [
            {
                "author": {
                    "name": f"{author_name} (@{handle})",
                    "url": f"https://bsky.app/profile/{handle}",
                },
                "description": text[:4000] if text else "(画像やリンクのみの投稿)",
                "url": url,
                "color": 0x1185FE,
            }
        ]
    }
    res = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    res.raise_for_status()


def main() -> None:
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set.")

    last_seen = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            last_seen = f.read().strip()

    res = requests.get(
        FEED_URL,
        params={"actor": ACTOR, "limit": 15},
        timeout=15,
    )
    res.raise_for_status()
    feed = res.json().get("feed", [])

    own_items = []
    for item in feed:
        if item.get("reason") is not None:
            continue
        post = item.get("post", {})
        uri = post.get("uri", "")
        if uri:
            own_items.append(post)

    if not own_items:
        return

    latest_uri = own_items[0]["uri"]

    if not last_seen:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(latest_uri + "\n")
        print(f"Initialized last_seen with: {latest_uri}")
        return

    new_posts = []
    for post in own_items:
        if post["uri"] == last_seen:
            break
        new_posts.append(post)

    for post in reversed(new_posts):
        record = post.get("record", {})
        author = post.get("author", {})
        handle = author.get("handle", ACTOR)
        display_name = author.get("displayName") or handle
        text = record.get("text", "")
        url = uri_to_url(post["uri"], handle)
        post_to_discord(text, url, display_name, handle)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(latest_uri + "\n")

    print(f"Posted {len(new_posts)} new post(s).")


if __name__ == "__main__":
    main()
