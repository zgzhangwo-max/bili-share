# -*- coding: utf-8 -*-
"""GitHub Actions 定时运行: 刷新B站视频CDN直链到 latest.json"""
import json
import time
import urllib.request

BVID = "BV1rzt26gEto"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def api(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA,
                      "Referer": "https://www.bilibili.com"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


view = api("https://api.bilibili.com/x/web-interface/view?bvid=" + BVID)
page = view["data"]["pages"][0]
pu = api("https://api.bilibili.com/x/player/playurl"
         f"?bvid={BVID}&cid={page['cid']}&qn=80"
         "&fnval=0&platform=html5&high_quality=1")
url = pu["data"]["durl"][0]["url"]
with open("latest.json", "w", encoding="utf-8") as f:
    json.dump({"url": url, "title": view["data"]["title"],
               "ts": int(time.time())}, f, ensure_ascii=False)
print("refreshed:", url[:70])
