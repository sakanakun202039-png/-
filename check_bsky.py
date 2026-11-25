import os
import requests

ACTOR = "489wiki.bsky.social"
SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
FEED_URL = "https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed"
STATE_FILE = "last_seen.txt"

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_APP_PASSWORD = os.environ.get("BSKY_APP_PASSWORD")


def uri_to_url(uri: str, handle: str) -> str:
    rkey = uri.rstrip("/").split("/")[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def get_access_token() -> str:
    if not BSKY_HANDLE or not BSKY_APP_PASSWORD:
        raise RuntimeError("BSKY_HANDLE or BSKY_APP_PASSWORD is not set.")
    res = requests.post(
        SESSION_URL,
        json={"identifier": BSKY_HANDLE, "password": BSKY_APP_PASSWORD},
        timeout=15,
    )
    res.raise_for_status()
    return res.json()["accessJwt"]


def extract_image_urls(post: dict) -> list[str]:
    """投稿データから画像URLのリストを取り出す（引用リポスト内も含む）"""
    urls: list[str] = []
    embed = post.get("embed") or {}
    embed_type = embed.get("$type", "")

    if embed_type == "app.bsky.embed.images#view":
        for img in embed.get("images", []):
            img_url = img.get("fullsize") or img.get("thumb")
            if img_url:
                urls.append(img_url)
    elif embed_type == "app.bsky.embed.recordWithMedia#view":
        media = embed.get("media") or {}
        if media.get("$type") == "app.bsky.embed.images#view":
            for img in media.get("images", []):
                img_url = img.get("fullsize") or img.get("thumb")
                if img_url:
                    urls.append(img_url)

    return urls


def post_to_discord(
    text: str, url: str, author_name: str, handle: str, image_urls: list[str]
) -> None:
    main_embed = {
        "author": {
            "name": f"{author_name} (@{handle})",
            "url": f"https://bsky.app/profile/{handle}",
        },
        "description": text[:4000] if text else ("(画像のみの投稿)" if image_urls else "(リンクのみの投稿)"),
        "url": url,
        "color": 0x1185FE,
    }

    embeds = [main_embed]

    if image_urls:
        # 1枚目はメインの埋め込みに添付
        main_embed["image"] = {"url": image_urls[0]}
        # 2枚目以降も同じurlを指定するとDiscord上で複数画像としてまとまりやすい
        for extra_url in image_urls[1:4]:
            embeds.append({
                "url": url,
                "image": {"url": extra_url},
                "color": 0x1185FE,
            })

    payload = {"embeds": embeds}
    res = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    res.raise_for_status()


def main() -> None:
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set.")

    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    last_seen = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            last_seen = f.read().strip()

    res = requests.get(
        FEED_URL,
        headers=headers,
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
        image_urls = extract_image_urls(post)
        post_to_discord(text, url, display_name, handle, image_urls)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(latest_uri + "\n")

    print(f"Posted {len(new_posts)} new post(s).")


if __name__ == "__main__":
    main()
