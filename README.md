# 礼品卡 paymentCode 多线程枚举工具

## 用途

礼品卡卡密后4位被错误设为 `0000`，遍历 `0000~9999` 找回正确值。支持**肯德基**和**必胜客**。

## 原理

1. 通过反编译小程序源码，提取 `kbsv` 签名算法：
   ```
   kbsv = MD5( client_key + "\t" + client_sec + "\t" + timestamp
               + "\t" + "/card/queryRealCardInfo" + "\t\t" + JSON(body) )
   ```
2. 枚举 `paymentCode` 后4位，逐个发送请求。
3. 根据返回的 `errCode` 判断结果：

| errCode | 含义 | 处理 |
|---------|------|------|
| `0` | 兑换成功 | ✅ 停止，保存结果 |
| `541` | 卡号或密码错误 | 跳过继续 |
| 其他 | 拥堵 / 超时等 | 等3秒后重试（最多5次） |

## 使用方法

### 1. 选择配置文件

根据品牌选择对应配置，改名为 `config.json`：

**肯德基** — 默认 `config.json` 已是肯德基配置

**必胜客** — 将 `config.pizzahut.json` 复制为 `config.json`：
```bash
copy config.pizzahut.json config.json
```

### 2. 填写配置

编辑 `config.json`，填入卡号、密码前缀、token：

**肯德基 config.json：**
```json
{
    "cardSequence": "",
    "paymentPrefix": "",
    "token": "",
    "openId": "omxHq0Jd7YT4IAQqpos_7StS_e4M",

    "secretKey": "kfc",
    "encodeList": ["smsCode"],
    "referer": "https://servicewechat.com/wx08ee7f7d36a2eff8/455/page-frame.html",
    "host": "appcamp.kfc.com.cn",

    "clientKey": "wxaupllQI8zMn8m8",
    "clientSec": "6nVSIvoC16X1kaVl",
    "signPath": "/card/queryRealCardInfo",
    "fullUrl": "https://appcamp.kfc.com.cn/api/card/queryRealCardInfo",

    "threads": 20,
    "maxRetry": 5,
    "retryWait": 3
}
```

**必胜客 config.json：**
```json
{
    "cardSequence": "",
    "paymentPrefix": "",
    "token": "",
    "openId": "",

    "secretKey": "ph",
    "encodeList": [],
    "referer": "https://servicewechat.com/wx534b0be83d03a625/458/page-frame.html",
    "host": "appmall.pizzahut.com.cn",

    "clientKey": "wxau5PW6sWIwx7nQ",
    "clientSec": "5opsk5ClazpBfq8B",
    "signPath": "/card/queryRealCardInfo",
    "fullUrl": "https://appmall.pizzahut.com.cn/api/card/queryRealCardInfo",

    "threads": 20,
    "maxRetry": 5,
    "retryWait": 3
}
```

**参数说明：**

| 参数 | 说明 | KFC | 必胜客 |
|------|------|-----|--------|
| `cardSequence` | 卡号 | `D0021...` | 卡号 |
| `paymentPrefix` | 密码前16位 | `210010...` | `210010...` |
| `token` | 登录凭证（抓包获取，有时效性） | - | - |
| `openId` | 微信 openId | 需填写 | 留空 |
| `secretKey` | 品牌标识 | `kfc` | `ph` |
| `encodeList` | 编码列表 | `["smsCode"]` | `[]` |
| `threads` | 并发线程数（建议 10~30） | `20` | `20` |
| `maxRetry` | 单个卡密最大重试次数 | `5` | `5` |
| `retryWait` | 重试前等待秒数 | `3` | `3` |

> `clientKey`、`clientSec`、`signPath`、`fullUrl`、`referer`、`host` 为签名/请求参数，已预填好，一般无需修改。

### 3. 运行

**Go 版本：**
```bash
kfc_enum.exe
```

**Python 版本：**
```bash
pip install requests
python kfc_enum.py
```

> ⚠️ `config.json` 必须与可执行程序在同一目录

### 4. 结果

找到后自动保存到 `found_payment.txt`：
```
卡号(cardSequence): D0021IJD84HI3QE0000
密码(paymentCode):   2100102248282520032
响应: {...}
```

## 如何抓取 token

1. PC 微信打开对应小程序（KFC / 必胜客），进入礼品卡页面
2. 用 Fiddler / Reqable 抓包
3. 找到 `queryRealCardInfo` 请求
4. 从请求体中提取 `token`、`cardSequence`

> ⚠️ token 有时效性，过期后脚本会返回 `4000099 签名认证失败` 或 `登录信息过期`，需重新抓包

## 从源码编译

```bash
go build -ldflags "-s -w" -trimpath -o kfc_enum.exe kfc_enum.go
```

## 输出示例

```
============================================================
礼品卡 paymentCode 多线程枚举 [肯德基 KFC]
============================================================
卡号(cardSequence): D0021IJD84HI3QE0000
密码前缀:           210010224828252
枚举范围:           2100102248282520000 ~ 2100102248282529999
接口地址:           https://appcamp.kfc.com.cn/api/card/queryRealCardInfo
线程数:             20
最大重试:           5 次
成功条件:           errCode = 0
============================================================

[2100102248282520000] EGC系统提示:541(卡号或密码输入错误)
[2100102248282520001] EGC系统提示:541(卡号或密码输入错误)
...

============================================================
>>> ✅ 兑换成功!
>>> 卡号: D0021IJD84HI3QE0000
>>> 密码: 2100102248282520032
>>> 响应: {"errCode":0,...}
============================================================
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `kfc_enum.exe` | Go 编译后的可执行程序 |
| `kfc_enum.go` | Go 源代码 |
| `kfc_enum.py` | Python 版本（需安装 requests） |
| `config.json` | 肯德基配置文件 |
| `config.pizzahut.json` | 必胜客配置文件（使用时改名为 config.json） |
| `found_payment.txt` | 找到后自动生成的结果文件 |
| `README.md` | 本说明文档 |

## 注意事项

- 仅用于找回自己名下礼品卡的错误卡密
- token 有时效性，过期需重新抓包
- 线程数过高可能触发限流，脚本会自动等待重试
- ⚠️ 必胜客未经实际兑换测试，不保证可用性
