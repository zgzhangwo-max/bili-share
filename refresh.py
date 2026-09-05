# -*- coding: utf-8 -*-
"""GitHub Actions 定时运行: 刷新B站视频CDN直链到 latest.json
v2: 针对数据中心IP风控加固 —— Cookie预热(buvid3) + 重试 + 双策略"""
import http.cookiejar
import json
import time
import urllib.request

BVID = "BV1rzt26gEto"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA,
        "Referer": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9"}

_cj = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_cj))


def api(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with _opener.open(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:              # noqa: BLE001
            last = e
            print(f"retry {i + 1}: {url[:60]} -> {e}")
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"api failed: {url[:60]}: {last}")


def bootstrap():
    """先拿 buvid3/buvid4 Cookie，模拟浏览器过风控"""
    try:
        api("https://api.bilibili.com/x/frontend/finger/spi", tries=1)
        print("bootstrap ok, cookies:", len(_cj))
    except Exception as e:                  # noqa: BLE001
        print("bootstrap warn:", e)


def main():
    bootstrap()
    view = api("https://api.bilibili.com/x/web-interface/view?bvid="
               + BVID)
    if view.get("code") != 0:
        raise RuntimeError(f"view code={view.get('code')} "
                           f"{view.get('message')}")
    page = view["data"]["pages"][0]
    cid = page["cid"]
    title = view["data"]["title"]

    # 策略: html5 单文件MP4 -> pc 单文件，取第一个成功的
    for params in ("qn=80&fnval=0&platform=html5&high_quality=1",
                   "qn=80&fnval=0&platform=pc&high_quality=1"):
        try:
            pu = api("https://api.bilibili.com/x/player/playurl"
                     f"?bvid={BVID}&cid={cid}&{params}")
            durl = (pu.get("data") or {}).get("durl") or []
            if pu.get("code") == 0 and durl:
                out = {"url": durl[0]["url"], "title": title,
                       "ts": int(time.time())}
                with open("latest.json", "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False)
                print("OK:", out["url"][:70])
                return
            print(f"strategy warn code={pu.get('code')} "
                  f"{pu.get('message')}")
        except Exception as e:              # noqa: BLE001
            print("strategy error:", e)
    raise RuntimeError("all strategies failed")


main()
