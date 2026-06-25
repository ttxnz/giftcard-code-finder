# KFC 礼品卡 paymentCode 多线程枚举脚本

## 用途

礼品卡卡密后4位被错误设为 `0000`，遍历 `0000~9999` 找回正确值。

## 原理

1. 通过反编译 KFC 小程序源码，提取 `kbsv` 签名算法：
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

### 1. 配置参数

编辑同目录下的 `config.json`：

```json
{
    "cardSequence": "",
    "paymentPrefix": "",
    "token": "",
    "openId": "omxHq0Jd7YT4IAQqpos_7StS_e4M",

    "clientKey": "wxaupllQI8zMn8m8",
    "clientSec": "6nVSIvoC16X1kaVl",
    "signPath": "/card/queryRealCardInfo",
    "fullUrl": "https://appcamp.kfc.com.cn/api/card/queryRealCardInfo",

    "threads": 20,
    "maxRetry": 5,
    "retryWait": 3
}
```

**参数说明：**

| 参数 | 说明 | 例子 |
|------|------|------|
| `cardSequence` | 卡号（带字母） | `D0021IJD84HI3QE0000` |
| `paymentPrefix` | 密码前16位，后4位由脚本枚举 | `210010224828252` |
| `token` | 登录凭证（从抓包获取，有时效性） | `25ee4ea98b88...` |
| `openId` | 微信 openId，一般不用改 | `omxHq0Jd7YT4...` |
| `threads` | 并发线程数（太多可能被限流，建议 10~30） | `20` |
| `maxRetry` | 单个卡密最大重试次数 | `5` |
| `retryWait` | 重试前等待秒数 | `3` |

> `clientKey`、`clientSec`、`signPath`、`fullUrl` 为 kbsv 签名参数，从反编译源码提取，一般无需修改。

### 2. 运行

```bash
kfc_enum.exe
```

> ⚠️ `config.json` 必须与 `kfc_enum.exe` 在同一目录

### 3. 结果

找到后自动保存到 `found_payment.txt`，格式：
```
卡号(cardSequence): D0021IJD84HI3QE0000
密码(paymentCode):   2100102248282520032
响应: {...}
```

## 如何抓取 token

1. PC 微信打开 KFC 小程序，进入礼品卡页面
2. 用 Fiddler / Reqable 抓包
3. 找到 `queryRealCardInfo` 请求
4. 从请求头/请求体中提取 `token`、`cardSequence`、`openId`

> ⚠️ token 有时效性，过期后脚本会返回 `4000099 签名认证失败` 或 `登录信息过期`，需重新抓包

## 从源码编译

```bash
go build -o kfc_enum.exe kfc_enum.go
```

## 输出示例

```
============================================================
KFC 礼品卡 paymentCode 多线程枚举
============================================================
卡号(cardSequence): D0021IJD84HI3QE0000
密码前缀:           210010224828252
枚举范围:           2100102248282520000 ~ 2100102248282529999
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
| `kfc_enum.exe` | 编译后的可执行程序 |
| `kfc_enum.go` | Go 源代码 |
| `config.json` | 配置文件 |
| `found_payment.txt` | 找到后自动生成的结果文件 |
| `README.md` | 本说明文档 |

## 注意事项

- 仅用于找回自己名下礼品卡的错误卡密
- token 有时效性，过期需重新抓包
- 线程数过高可能触发限流，脚本会自动等待重试
