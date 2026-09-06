# -*- coding: utf-8 -*-
"""GitHub Actions 定时运行: 刷新B站视频CDN直链到 latest.json
v3: 修复 buvid3 获取方式(spi 在 JSON body 返回, 非 Set-Cookie)
    + status.json 自检文件(失败原因可远程读取) + CORS代理兜底"""
import json
import time
import traceback
import urllib.parse
import urllib.request

BVID = "BV17Ubn6wEus"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
BASE_HDRS = {"User-Agent": UA,
             "Referer": "https://www.bilibili.com",
             "Accept": "application/json, text/plain, */*",
             "Accept-Language": "zh-CN,zh;q=0.9"}


def api(url, cookie="", tries=3, raw=False):
    last = None
    for i in range(tries):
        try:
            h = dict(BASE_HDRS)
            if cookie:
                h["Cookie"] = cookie
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read()
            return body if raw else json.loads(body)
        except Exception as e:              # noqa: BLE001
            last = e
            print(f"retry {i + 1}: {url[:70]} -> {e}")
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{url[:70]} -> {last}")


def get_cookie():
    """spi 接口把 buvid3/buvid4 放在 JSON body 里，需手动拼 Cookie"""
    spi = api("https://api.bilibili.com/x/frontend/finger/spi", tries=2)
    d = spi.get("data") or {}
    return (f"buvid3={d.get('b_3', '')}; buvid4={d.get('b_4', '')}; "
            f"b_nut={int(time.time())}")


def main():
    cookie = get_cookie()
    print("buvid3 cookie ready")

    view = api("https://api.bilibili.com/x/web-interface/view?bvid="
               + BVID, cookie)
    if view.get("code") != 0:
        raise RuntimeError(f"view code={view.get('code')} "
                           f"{view.get('message')}")
    page = view["data"]["pages"][0]
    cid = page["cid"]
    title = view["data"]["title"]

    strategies = [
        ("direct-html5",
         f"https://api.bilibili.com/x/player/playurl?bvid={BVID}"
         f"&cid={cid}&qn=80&fnval=0&platform=html5&high_quality=1",
         cookie),
        ("direct-pc",
         f"https://api.bilibili.com/x/player/playurl?bvid={BVID}"
         f"&cid={cid}&qn=80&fnval=0&platform=pc&high_quality=1",
         cookie),
        # 数据中心 IP 被 B 站风控时的兜底: 经公共 CORS 代理中转
        ("proxy-html5",
         "https://api.allorigins.win/raw?url=" + urllib.parse.quote(
             f"https://api.bilibili.com/x/player/playurl?bvid={BVID}"
             f"&cid={cid}&qn=80&fnval=0&platform=html5&high_quality=1",
             safe=""),
         ""),
    ]
    errors = []
    for name, url, ck in strategies:
        try:
            pu = api(url, ck)
            durl = (pu.get("data") or {}).get("durl") or []
            if pu.get("code") != 0 or not durl:
                errors.append(f"{name}: code={pu.get('code')} "
                              f"{pu.get('message')}")
                continue
            seg = durl[0]
            # 逐条裸探(不带Referer)，保证家长浏览器直接能播
            cands = [seg["url"]] + list(seg.get("backup_url") or [])
            picked = None
            for cu in cands:
                try:
                    h = {"User-Agent": UA, "Range": "bytes=0-0"}
                    req = urllib.request.Request(cu, headers=h)
                    with urllib.request.urlopen(req, timeout=12) as rr:
                        if rr.status in (200, 206):
                            picked = cu
                            break
                except Exception:           # noqa: BLE001
                    continue
            if not picked:
                errors.append(f"{name}: 所有候选节点裸探失败")
                continue
            out = {"url": picked, "title": title,
                   "ts": int(time.time())}
            with open("latest.json", "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False)
            print(f"OK via {name}:", picked[:70])
            return {"ok": True, "via": name,
                    "url_head": picked[:80], "title": title}
        except Exception as e:              # noqa: BLE001
            errors.append(f"{name}: {e}")
    raise RuntimeError("all strategies failed | " + " ; ".join(errors))


try:
    result = main()
except Exception:
    result = {"ok": False, "error": traceback.format_exc()[-1200:]}
    print(result["error"])

result["ts"] = int(time.time())
with open("status.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
