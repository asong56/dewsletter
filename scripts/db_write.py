import os
import time
import requests
import statistics
import google.generativeai as genai


TEST_URLS = [
    "https://vercel.com",
    "https://cloudflare.com",
    "https://github.com",
    "https://google.com",
    "https://youtube.com",
]

STABILITY_ROUNDS = 5
MIN_SUCCESS_RATE = 0.6  # 低于这个成功率的代理直接丢弃


def fetch_proxies_from_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = """
Return 100 proxy servers in plain text format.
One per line.
Format: ip:port
No explanation.
No markdown.
"""

    resp = model.generate_content(prompt)

    proxies = [
        line.strip()
        for line in resp.text.splitlines()
        if ":" in line
    ]

    return proxies[:100]


def test_once(proxy, url):
    proxies = {
        "http": proxy,
        "https": proxy,
    }

    start = time.time()

    try:
        r = requests.get(
            url,
            proxies=proxies,
            timeout=8
        )

        latency = time.time() - start

        if r.status_code != 200:
            return False, latency

        return True, latency

    except Exception:
        return False, None


def validate_proxy(proxy):
    """对所有 TEST_URLS 各测一次，不做 fail-fast，返回(成功数, 总数, 成功请求的延迟列表)"""
    successes = 0
    latencies = []

    for url in TEST_URLS:
        ok, latency = test_once(proxy, url)

        if ok:
            successes += 1
            if latency:
                latencies.append(latency)

    return successes, len(TEST_URLS), latencies


def stability_test(proxy):
    """跑 STABILITY_ROUNDS 轮，统计真实的成功率，而不是恒为 1.0"""
    total_success = 0
    total_checks = 0
    all_latencies = []

    for _ in range(STABILITY_ROUNDS):
        successes, total, latencies = validate_proxy(proxy)

        total_success += successes
        total_checks += total
        all_latencies.extend(latencies)

        time.sleep(0.2)

    if not all_latencies:
        return None  # 一次都没成功过，没有意义的延迟数据

    success_rate = total_success / total_checks

    if success_rate < MIN_SUCCESS_RATE:
        return None

    return {
        "proxy": proxy,
        "success_rate": success_rate,
        "avg_latency": statistics.mean(all_latencies),
    }


def main():
    candidates = fetch_proxies_from_gemini()

    valid = []

    for p in candidates:
        print("testing:", p)

        result = stability_test(p)

        if result:
            valid.append(result)

    # 排序：稳定性优先，延迟次之（现在 success_rate 是真实值，排序才有意义）
    valid.sort(
        key=lambda x: (-x["success_rate"], x["avg_latency"])
    )

    with open("proxy.txt", "w") as f:
        for v in valid:
            f.write(v["proxy"] + "\n")

    print("valid:", len(valid))


if __name__ == "__main__":
    main()
