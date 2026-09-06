# -*- coding: utf-8 -*-
"""GitHub Actions 定时运行: 批量刷新 videos/ 下所有视频的CDN直链
v4: 多视频库架构 —— 扫描 videos/*.json 逐个刷新 + 重建视频库清单"""
import glob
import json
import os
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
BASE_HDRS = {"User-Agent": UA,
             "Referer": "https://www.bilibili.com",
             "Accept": "application/json, text/plain, */*",
             "Accept-Language": "zh-CN,zh;q=0.9"}


def api(url, cookie="", tries=3):
    last = None
    for i in range(tries):
        try:
            h = dict(BASE_HDRS)
            if cookie:
                h["Cookie"] = cookie
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:              # noqa: BLE001
            last = e
            print(f"retry {i + 1}: {url[:70]} -> {e}")
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{url[:70]} -> {last}")


def get_cookie():
    spi = api("https://api.bilibili.com/x/frontend/finger/spi", tries=2)
    d = spi.get("data") or {}
    return (f"buvid3={d.get('b_3', '')}; buvid4={d.get('b_4', '')}; "
            f"b_nut={int(time.time())}")


def bare_ok(u):
    """裸探(不带Referer)：家长浏览器必须直接能播"""
    try:
        h = {"User-Agent": UA, "Range": "bytes=0-0"}
        req = urllib.request.Request(u, headers=h)
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status in (200, 206)
    except Exception:                       # noqa: BLE001
        return False


def fresh_url(bvid, page_no, cookie):
    view = api("https://api.bilibili.com/x/web-interface/view?bvid="
               + bvid, cookie)
    if view.get("code") != 0:
        raise RuntimeError(f"view code={view.get('code')}")
    pages = view["data"]["pages"]
    p = pages[min(max(page_no - 1, 0), len(pages) - 1)]
    cid = p["cid"]
    q = (f"bvid={bvid}&cid={cid}&qn=80&fnval=0"
         "&platform=html5&high_quality=1")
    strategies = [
        ("html5", f"https://api.bilibili.com/x/player/playurl?{q}",
         cookie),
        ("pc", "https://api.bilibili.com/x/player/playurl?"
         + q.replace("html5", "pc"), cookie),
        ("proxy", "https://api.allorigins.win/raw?url="
         + urllib.parse.quote(
             "https://api.bilibili.com/x/player/playurl?" + q,
             safe=""), ""),
    ]
    errs = []
    for name, url, ck in strategies:
        try:
            pu = api(url, ck)
            durl = (pu.get("data") or {}).get("durl") or []
            if pu.get("code") != 0 or not durl:
                errs.append(f"{name}: code={pu.get('code')}")
                continue
            seg = durl[0]
            for cu in [seg["url"]] + list(seg.get("backup_url") or []):
                if bare_ok(cu):
                    return cu, view["data"]["title"], name
            errs.append(f"{name}: bare-probe failed")
        except Exception as e:              # noqa: BLE001
            errs.append(f"{name}: {str(e)[:100]}")
    raise RuntimeError("; ".join(errs))


def main():
    cookie = get_cookie()
    files = sorted(p for p in glob.glob("videos/*.json")
                   if os.path.basename(p) != "index.json")
    results = []
    for path in files:
        d = json.load(open(path, encoding="utf-8"))
        bvid = d.get("bvid") or os.path.basename(path)[:-5]
        try:
            url, title, via = fresh_url(bvid, int(d.get("page", 1)),
                                        cookie)
            d.update(bvid=bvid, title=title, url=url,
                     ts=int(time.time()))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            results.append({"bvid": bvid, "ok": True, "via": via})
            print("OK", bvid, url[:60])
        except Exception as e:              # noqa: BLE001
            results.append({"bvid": bvid, "ok": False,
                            "error": str(e)[:300]})
            print("FAIL", bvid, e)
    # 重建视频库清单（主页列表用）
    vids = []
    for path in files:
        d = json.load(open(path, encoding="utf-8"))
        vids.append({"key": d.get("bvid"),
                     "title": d.get("title", "")})
    os.makedirs("videos", exist_ok=True)
    with open("videos/index.json", "w", encoding="utf-8") as f:
        json.dump({"videos": vids, "ts": int(time.time())}, f,
                  ensure_ascii=False)
    status = {"ok": all(r["ok"] for r in results),
              "count": len(results), "results": results,
              "ts": int(time.time())}
    with open("status.json", "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    print("done:", len(results), "videos")


main()
