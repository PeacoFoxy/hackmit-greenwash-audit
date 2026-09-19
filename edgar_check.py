"""
EDGAR Form 4 可行性验证脚本
=============================
运行前：pip install requests
必须修改下面的 UA 为你的真实姓名和邮箱，否则 SEC 会返回 403。

跑完看最后的 GO / NO-GO 结论。
"""

import json
import time
import requests
from xml.etree import ElementTree as ET

UA = {"User-Agent": "wh2678@nyu.edu"}


SEC = "https://www.sec.gov"
DATA = "https://data.sec.gov"
TICKER = "AAPL"
# 用最近一个交易日（周一到周五，非节假日）
INDEX_DATE = "20260918"
INDEX_QTR = "2026/QTR3"

results = {}


def get(url, as_json=False):
    """带限速的请求。SEC 限制每秒 10 次，我们放慢到 3 次/秒。"""
    time.sleep(0.35)
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json() if as_json else r.text


# ---------------------------------------------------------------
# STEP 1: ticker -> CIK，然后拉这家公司的申报列表
# ---------------------------------------------------------------
print("\n" + "=" * 60)
print("STEP 1: ticker -> CIK -> submissions API")
print("=" * 60)

try:
    tickers = get(f"{SEC}/files/company_tickers.json", as_json=True)
    cik = None
    for row in tickers.values():
        if row["ticker"] == TICKER:
            cik = str(row["cik_str"]).zfill(10)
            print(f"  [ok] {TICKER} -> CIK {cik} ({row['title']})")
            break
    if cik is None:
        raise RuntimeError(f"没找到 {TICKER}")

    sub = get(f"{DATA}/submissions/CIK{cik}.json", as_json=True)
    recent = sub["filings"]["recent"]
    n = len(recent["form"])
    print(f"  [ok] 拿到 {n} 条近期申报")

    # 关键检查：Form 4 在不在里面
    form4_idx = [i for i in range(n) if recent["form"][i] == "4"]
    print(f"  Form 4 数量: {len(form4_idx)}")

    if form4_idx:
        i = form4_idx[0]
        acc = recent["accessionNumber"][i]
        print(f"  最近一份 Form 4:")
        print(f"    accession      : {acc}")
        print(f"    filingDate     : {recent['filingDate'][i]}")
        print(f"    acceptanceTime : {recent['acceptanceDateTime'][i]}   <-- PIT 时间戳")
        results["step1"] = True
        results["cik"] = cik
        results["accession"] = acc
    else:
        print("  [!] 这家公司的 submissions 里没有 Form 4。")
        print("      不一定是坏事——STEP 3 的 daily index 一定有，届时从那里取。")
        results["step1"] = "partial"

except Exception as e:
    print(f"  [FAIL] {e}")
    results["step1"] = False


# ---------------------------------------------------------------
# STEP 2: 下载一份 Form 4 XML，检查字段
# ---------------------------------------------------------------
print("\n" + "=" * 60)
print("STEP 2: 下载 Form 4 XML 并解析字段")
print("=" * 60)

try:
    if not results.get("accession"):
        raise RuntimeError("STEP 1 没拿到 accession，跳过")

    cik_short = str(int(results["cik"]))          # 去掉前导零
    acc_nodash = results["accession"].replace("-", "")
    folder = f"{SEC}/Archives/edgar/data/{cik_short}/{acc_nodash}"

    # 列出这份申报的所有文件，找出 ownership XML
    listing = get(f"{folder}/index.json", as_json=True)
    names = [it["name"] for it in listing["directory"]["item"]]
    print(f"  目录内文件: {names}")

    xmls = [x for x in names
            if x.endswith(".xml")
            and not x.startswith("xsl")          # xsl 开头的是渲染版，不是原始数据
            and "index" not in x.lower()]
    if not xmls:
        raise RuntimeError("目录里没有原始 XML")

    raw = get(f"{folder}/{xmls[0]}")
    root = ET.fromstring(raw)
    print(f"  [ok] 解析成功，根节点 <{root.tag}>")

    def find(path):
        el = root.find(path)
        return el.text if el is not None else None

    def find_deep(parent, tag):
        """字段有时套在 <value> 里，有时不套"""
        el = parent.find(tag)
        if el is None:
            return None
        v = el.find("value")
        return (v.text if v is not None else el.text)

    print("\n  --- 关键字段 ---")
    print(f"  期间          : {find('periodOfReport')}")
    print(f"  发行人        : {find('issuer/issuerName')}")
    print(f"  代码          : {find('issuer/issuerTradingSymbol')}")
    print(f"  发行人 CIK    : {find('issuer/issuerCik')}")

    owner = root.find("reportingOwner")
    if owner is not None:
        print(f"  申报人        : {find('reportingOwner/reportingOwnerId/rptOwnerName')}")
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            print(f"    isDirector      : {find_deep(rel, 'isDirector')}")
            print(f"    isOfficer       : {find_deep(rel, 'isOfficer')}")
            print(f"    isTenPercentOwner: {find_deep(rel, 'isTenPercentOwner')}")
            print(f"    officerTitle    : {find_deep(rel, 'officerTitle')}")

    txns = root.findall("nonDerivativeTable/nonDerivativeTransaction")
    print(f"\n  非衍生品交易条数: {len(txns)}")
    for t in txns[:3]:
        code = find_deep(t.find("transactionCoding"), "transactionCode")
        amt = t.find("transactionAmounts")
        print(f"    date={find_deep(t, 'transactionDate')} "
              f"code={code} "
              f"shares={find_deep(amt, 'transactionShares')} "
              f"price={find_deep(amt, 'transactionPricePerShare')} "
              f"A/D={find_deep(amt, 'transactionAcquiredDisposedCode')}")

    derivs = root.findall("derivativeTable/derivativeTransaction")
    print(f"  衍生品交易条数  : {len(derivs)}")

    results["step2"] = len(txns) > 0 or len(derivs) > 0

except Exception as e:
    print(f"  [FAIL] {e}")
    results["step2"] = False


# ---------------------------------------------------------------
# STEP 3: daily index —— 能否构造完整历史面板
# ---------------------------------------------------------------
print("\n" + "=" * 60)
print("STEP 3: daily index（决定能否构造历史面板）")
print("=" * 60)

try:
    url = f"{SEC}/Archives/edgar/daily-index/{INDEX_QTR}/form.{INDEX_DATE}.idx"
    txt = get(url)
    lines = txt.splitlines()
    print(f"  [ok] 拿到 {len(lines)} 行")

    form4_lines = [l for l in lines if l.strip().startswith("4 ")]
    print(f"  当天 Form 4 数量: {len(form4_lines)}")
    print("  前 3 行示例:")
    for l in form4_lines[:3]:
        print(f"    {l[:110]}")

    results["step3"] = len(form4_lines) > 0

except Exception as e:
    print(f"  [FAIL] {e}")
    print(f"  提示: {INDEX_DATE} 必须是交易日。周末/节假日没有 index 文件。")
    print(f"  可先看有哪些文件: {SEC}/Archives/edgar/daily-index/{INDEX_QTR}/index.json")
    results["step3"] = False


# ---------------------------------------------------------------
# 结论
# ---------------------------------------------------------------
print("\n" + "=" * 60)
print("结论")
print("=" * 60)
print(f"  STEP 1 (submissions + 时间戳): {results.get('step1')}")
print(f"  STEP 2 (XML 字段可解析)      : {results.get('step2')}")
print(f"  STEP 3 (daily index 可批量)  : {results.get('step3')}")

if results.get("step2") and results.get("step3"):
    print("\n  >>> GO. 项目成立，可以开始。")
elif results.get("step2"):
    print("\n  >>> 部分通过。单份能解析但批量有问题，检查 STEP 3 的日期。")
else:
    print("\n  >>> NO-GO. 把完整报错贴回聊天，十分钟内换方案。")
