#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合肥大学生命健康与环境工程学院 通知监控机器人
功能：定时爬取学院最新通知 -> AI智能总结 -> 飞书机器人推送
"""

import json
import os
import sys
import time
import hashlib
import logging
import argparse
import base64
import hmac
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ============================================================
# 配置与日志
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(config_path=None):
    """加载配置文件，环境变量优先（适合CI/服务器部署）"""
    if config_path is None:
        config_path = os.path.join(SCRIPT_DIR, "config.json")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # 环境变量覆盖（优先级最高），适合 GitHub Actions / 服务器部署
    env_map = {
        "FEISHU_WEBHOOK": "feishu_webhook",
        "FEISHU_SECRET": "feishu_secret",
        "AI_API_KEY": "ai_api_key",
        "AI_API_BASE": "ai_api_base",
        "AI_MODEL": "ai_model",
        "LIST_URL": "list_url",
        "BASE_URL": "base_url",
    }
    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key, "").strip()
        if val:
            config[config_key] = val

    return config


def setup_logging(log_file):
    """配置日志：同时输出到控制台和文件"""
    log_path = os.path.join(SCRIPT_DIR, log_file)
    logger = logging.getLogger("hfuu_monitor")
    logger.setLevel(logging.INFO)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


# ============================================================
# 已推送记录管理
# ============================================================

def load_seen(seen_file):
    """加载已推送通知记录"""
    path = os.path.join(SCRIPT_DIR, seen_file)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen_file, seen_data):
    """保存已推送通知记录"""
    path = os.path.join(SCRIPT_DIR, seen_file)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen_data, f, ensure_ascii=False, indent=2)


def notice_id(url):
    """用URL的md5作为通知唯一标识"""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


# ============================================================
# 网页爬取
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def fetch_page(url, timeout=15):
    """抓取网页，自动跟随重定向"""
    resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    resp.encoding = resp.apparent_encoding or "utf-8"
    resp.raise_for_status()
    return resp.text


def parse_notice_list(html, base_url):
    """
    解析通知列表页，返回通知列表
    每条: {"title": str, "url": str, "date": str, "nid": str}
    """
    soup = BeautifulSoup(html, "html.parser")
    notices = []
    for li in soup.select("ul.wp_article_list > li.list_item"):
        title_tag = li.select_one(".Article_Title a")
        date_tag = li.select_one(".Article_PublishDate")
        if not title_tag:
            continue
        title = title_tag.get("title") or title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        url = urljoin(base_url, href)
        date = date_tag.get_text(strip=True) if date_tag else ""
        notices.append({
            "title": title,
            "url": url,
            "date": date,
            "nid": notice_id(url),
        })
    return notices


def parse_notice_detail(html):
    """
    解析通知详情页，返回正文文本和附件列表
    """
    soup = BeautifulSoup(html, "html.parser")

    # 标题
    title_tag = soup.select_one("h1.arti_title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # 发布时间
    date_tag = soup.select_one("span.arti_update")
    date = date_tag.get_text(strip=True).replace("发布时间：", "") if date_tag else ""

    # 正文
    content_tag = soup.select_one("div.wp_articlecontent")
    content_text = ""
    attachments = []
    if content_tag:
        # 提取附件链接
        for a in content_tag.select("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if href and (href.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"))
                         or "_upload/article/files" in href):
                attachments.append({"name": text or "附件", "url": href})
        # 提取纯文本
        content_text = content_tag.get_text(separator="\n", strip=True)

    # 清理多余空行
    content_text = "\n".join(line.strip() for line in content_text.splitlines() if line.strip())

    return {
        "title": title,
        "date": date,
        "content": content_text,
        "attachments": attachments,
    }


# ============================================================
# AI 智能总结
# ============================================================

def ai_summarize(title, content, config, logger):
    """
    调用AI大模型对通知进行智能总结
    未配置API key时降级为规则摘要
    """
    api_key = config.get("ai_api_key", "").strip()
    max_len = config.get("max_summary_length", 500)

    if not api_key:
        return rule_based_summary(title, content, max_len)

    try:
        api_base = config.get("ai_api_base", "https://ark.cn-beijing.volces.com/api/v3")
        model = config.get("ai_model", "doubao-1-5-pro-32k-250115")

        prompt = (
            f"你是一个高校通知摘要助手。请用简洁明了的中文总结以下学院通知，"
            f"突出关键信息（事项、时间、地点、对象、要求、截止日期等），"
            f"控制在{max_len}字以内，分点列出，不要废话。\n\n"
            f"【通知标题】{title}\n\n"
            f"【通知正文】\n{content[:3000]}\n"
        )

        resp = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 800,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        summary = data["choices"][0]["message"]["content"].strip()
        logger.info("AI总结成功")
        return summary
    except Exception as e:
        logger.warning(f"AI总结失败，降级为规则摘要: {e}")
        return rule_based_summary(title, content, max_len)


def rule_based_summary(title, content, max_len):
    """
    无AI时的降级方案：截取正文关键段落
    """
    if not content:
        return f"（本通知主要为附件形式，请点击链接查看详情）"

    # 取前几段有意义的内容
    lines = content.split("\n")
    summary_lines = []
    for line in lines:
        if len(line) > 5:
            summary_lines.append(line)
        if len("\n".join(summary_lines)) > max_len:
            break

    summary = "\n".join(summary_lines)
    if len(summary) > max_len:
        summary = summary[:max_len] + "..."
    return summary


# ============================================================
# 飞书机器人推送
# ============================================================

def gen_feishu_sign(secret, timestamp):
    """生成飞书机器人签名（配置了secret时需要）"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def build_feishu_card(notice, summary, config):
    """
    构建飞书消息卡片（interactive card）
    """
    title = notice["title"]
    date = notice.get("date", "")
    url = notice["url"]
    attachments = notice.get("attachments", [])

    # 附件文本
    attach_text = ""
    if attachments:
        attach_lines = []
        for att in attachments[:5]:
            att_url = urljoin(config["base_url"], att["url"]) if att["url"].startswith("/") else att["url"]
            attach_lines.append(f"- [{att['name']}]({att_url})")
        attach_text = "\n**附件：**\n" + "\n".join(attach_lines)

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📢 学院新通知 | {date}"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{title}**",
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📋 内容摘要**\n{summary}{attach_text}",
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔗 查看原文"},
                            "type": "primary",
                            "url": url,
                        }
                    ],
                },
            ],
        },
    }
    return card


def send_feishu(notice, summary, config, logger):
    """发送飞书消息"""
    webhook = config.get("feishu_webhook", "")
    if not webhook or "你的webhook" in webhook:
        logger.warning("飞书webhook未配置，跳过推送")
        return False

    try:
        payload = build_feishu_card(notice, summary, config)

        # 如果配置了secret，加签名
        secret = config.get("feishu_secret", "").strip()
        if secret:
            timestamp = str(int(time.time()))
            sign = gen_feishu_sign(secret, timestamp)
            payload["timestamp"] = timestamp
            payload["sign"] = sign

        resp = requests.post(webhook, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info(f"飞书推送成功: {notice['title'][:30]}")
            return True
        else:
            logger.error(f"飞书推送失败: {result}")
            return False
    except Exception as e:
        logger.error(f"飞书推送异常: {e}")
        return False


# ============================================================
# 主流程
# ============================================================

def run_once(config, logger, init_mode=False):
    """
    执行一次检查
    init_mode=True 时，只记录现有通知不推送（首次运行初始化）
    """
    logger.info("=" * 50)
    logger.info("开始检查学院通知...")

    # 1. 抓取列表页
    try:
        list_html = fetch_page(config["list_url"])
    except Exception as e:
        logger.error(f"抓取列表页失败: {e}")
        return

    notices = parse_notice_list(list_html, config["base_url"])
    logger.info(f"列表页解析到 {len(notices)} 条通知")

    if not notices:
        logger.warning("未解析到任何通知，请检查页面结构是否变化")
        return

    # 2. 加载已推送记录
    seen = load_seen(config["seen_file"])

    # 3. 筛选新通知（按日期倒序，最新的在前）
    new_notices = []
    for n in notices:
        if n["nid"] not in seen:
            new_notices.append(n)

    # 列表页通常按时间倒序，反转一下让旧的先处理
    new_notices.reverse()

    logger.info(f"发现 {len(new_notices)} 条新通知")

    if init_mode:
        # 初始化模式：全部标记为已读，不推送
        for n in notices:
            seen[n["nid"]] = {
                "title": n["title"],
                "url": n["url"],
                "date": n["date"],
                "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        save_seen(config["seen_file"], seen)
        logger.info(f"初始化完成，已记录 {len(notices)} 条现有通知（不推送）")
        return

    if not new_notices:
        logger.info("没有新通知，结束")
        return

    # 4. 逐条处理新通知
    for n in new_notices:
        logger.info(f"处理新通知: {n['title'][:40]}")

        # 抓取详情
        try:
            detail_html = fetch_page(n["url"])
            detail = parse_notice_detail(detail_html)
        except Exception as e:
            logger.error(f"抓取详情页失败: {e}")
            detail = {"title": n["title"], "date": n["date"], "content": "", "attachments": []}

        # 合并信息
        notice_full = {
            **n,
            "title": detail.get("title") or n["title"],
            "date": detail.get("date") or n["date"],
            "content": detail.get("content", ""),
            "attachments": detail.get("attachments", []),
        }

        # AI总结
        summary = ai_summarize(notice_full["title"], notice_full["content"], config, logger)

        # 飞书推送
        success = send_feishu(notice_full, summary, config, logger)

        # 无论推送成功与否都标记为已处理（避免重复推送失败的）
        # 如果推送失败，可以选择不标记，下次重试。这里标记为已处理但记录状态
        seen[n["nid"]] = {
            "title": notice_full["title"],
            "url": n["url"],
            "date": notice_full["date"],
            "pushed": success,
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_seen(config["seen_file"], seen)

        # 礼貌延迟，避免请求过快
        time.sleep(1)

    logger.info(f"本轮处理完成，共处理 {len(new_notices)} 条新通知")


def main():
    parser = argparse.ArgumentParser(description="合肥大学学院通知监控机器人")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--init", action="store_true", help="初始化模式：只记录现有通知不推送")
    parser.add_argument("--once", action="store_true", help="只运行一次（适合任务计划程序）")
    args = parser.parse_args()

    config = load_config(args.config)
    logger = setup_logging(config.get("log_file", "monitor.log"))

    logger.info("=" * 50)
    logger.info("合肥大学生命健康与环境工程学院 通知监控启动")
    logger.info(f"检查间隔: {config.get('check_interval_minutes', 30)} 分钟")
    logger.info(f"列表页: {config['list_url']}")

    if args.init:
        run_once(config, logger, init_mode=True)
        logger.info("初始化完成，请修改config.json配置飞书webhook后正常运行")
        return

    if args.once:
        run_once(config, logger, init_mode=False)
        return

    # 持续运行模式
    interval = config.get("check_interval_minutes", 30) * 60
    while True:
        try:
            run_once(config, logger, init_mode=False)
        except Exception as e:
            logger.error(f"主循环异常: {e}", exc_info=True)
        logger.info(f"等待 {interval // 60} 分钟后下次检查...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
