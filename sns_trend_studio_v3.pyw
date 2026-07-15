# -*- coding: utf-8 -*-
"""
============================================================
 SNS 트렌드 콘텐츠 스튜디오 v3.0  (GUI 앱, 100% 무료)
============================================================
 [v3.0 새 기능]
 - 분야 선택: 건강/경제/시사/IT과학/연예/스포츠/라이프/해외
 - 구글 뉴스 추가 (무료 RSS, 키 불필요) + 출처 구별 표시
 - 인기도 지수🔥: 뉴스 랭킹 상위노출 + 발행 최신성 기반
   (※ 정확한 조회수는 언론사가 비공개라 무료로 불가 → 지수로 대체)
 - 뉴스 더블클릭 → 기사 원문 사이트 자동 열기
 - AI 3사 버튼: 클로드/ChatGPT/제미나이 → 프롬프트 복사+사이트 오픈
 - 추가 라이브러리 설치 불필요 (파이썬 기본 기능만 사용)

 [다른 컴퓨터 설치] ① python.org 파이썬 설치("Add to PATH" 체크!)
                   ② 이 파일 복사 ③ 더블클릭
============================================================
"""
import os
import re
import json
import time
import threading
import webbrowser
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CHANNELS_PATH = os.path.join(BASE_DIR, "channels.json")
GUIDE_PATH = os.path.join(BASE_DIR, "guidelines.json")
HISTORY_PATH = os.path.join(BASE_DIR, "history.json")
RSS_PATH = os.path.join(BASE_DIR, "rss_sources.json")
IMG_DIR = os.path.join(BASE_DIR, "images")
PROMPT_DIR = os.path.join(BASE_DIR, "prompts")

AI_SITES = {
    "클로드": "https://claude.ai/new",
    "ChatGPT": "https://chatgpt.com/",
    "제미나이": "https://gemini.google.com/app",
}

# 분야별 수집 소스 정의 (구글뉴스 토픽 + 네이버 검색어 + 해외RSS 카테고리)
CATEGORIES = {
    "🎯 채널 맞춤(자동)": {"google": None, "naver": None, "rss": None},
    "💪 건강/피트니스":  {"google": "HEALTH", "naver": ["건강 운동", "다이어트"], "rss": "health"},
    "💰 경제/재테크":    {"google": "BUSINESS", "naver": ["경제", "재테크"], "rss": None},
    "🏛 시사/사회":      {"google": "NATION", "naver": ["사회 이슈"], "rss": None},
    "🤖 IT/과학":        {"google": "TECHNOLOGY", "naver": ["IT 기술", "AI 인공지능"], "rss": None},
    "🎬 연예/문화":      {"google": "ENTERTAINMENT", "naver": ["연예"], "rss": None},
    "⚽ 스포츠":         {"google": "SPORTS", "naver": ["스포츠"], "rss": None},
    "🌏 세계/해외":      {"google": "WORLD", "naver": ["국제 뉴스"], "rss": "lifestyle"},
    "☕ 라이프스타일":   {"google": None, "naver": ["라이프스타일 트렌드", "요즘 유행"], "rss": "lifestyle"},
}


# ==========================================================
# 데이터 파일 관리
# ==========================================================
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    save_json(path, default)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


DEFAULT_CONFIG = {
    "naver_client_id": "",
    "naver_client_secret": "",
    "hf_token": "",
    "news_per_source": 6
}

DEFAULT_CHANNELS = {
    "channels": [
        {
            "name": "바디컨피던스 계정",
            "tone": "전문적이고 당당하며, 올바른 건강관과 바디 포지티브(자존감/기능성 운동)를 심어주는 파워풀한 톤",
            "keywords": ["운동", "헬스", "피트니스", "다이어트", "건강", "근력", "체형", "자세", "단백질", "수면", "스트레스", "fitness", "workout", "health", "exercise", "wellness"],
            "image_style": "Energetic, powerful, confident professional fitness style, bold natural lighting, athletic pose, body positivity",
            "banned_words": ["치료", "완치", "질병 예방 보장", "100% 효과", "부작용 없음", "의사도 놀란"],
            "naver_queries": ["건강 운동", "다이어트 연구", "피트니스 트렌드"],
            "default_category": "💪 건강/피트니스",
            "rss_categories": ["health"]
        },
        {
            "name": "개인 일상 계정",
            "tone": "친근하고 공감 가며, 일상 속 인사이트를 나누는 따뜻한 소통형 톤",
            "keywords": ["일상", "라이프", "트렌드", "심리", "습관", "자기계발", "MZ", "직장", "취미", "여행", "lifestyle", "trend", "habit"],
            "image_style": "Warm, cozy, friendly lifestyle, modern and natural daily routine ambiance",
            "banned_words": [],
            "naver_queries": ["라이프스타일 트렌드", "MZ세대 일상", "요즘 유행"],
            "default_category": "☕ 라이프스타일",
            "rss_categories": ["lifestyle"]
        }
    ]
}

DEFAULT_RSS = {
    "health": [
        {"name": "BBC Health", "url": "http://feeds.bbci.co.uk/news/health/rss.xml"},
        {"name": "ScienceDaily Fitness", "url": "https://www.sciencedaily.com/rss/health_medicine/fitness.xml"},
        {"name": "Medical News Today", "url": "https://www.medicalnewstoday.com/rss/news.xml"}
    ],
    "lifestyle": [
        {"name": "Guardian Life&Style", "url": "https://www.theguardian.com/lifeandstyle/rss"},
        {"name": "BBC News (Top)", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
        {"name": "Psychology Today", "url": "https://www.psychologytoday.com/intl/rss.xml"}
    ]
}

DEFAULT_GUIDELINES = {
    "version": "1.0",
    "updated": "",
    "rules": [
        "뉴스는 반드시 '요약+출처 명시+내 채널 관점의 재해석' 구조로 쓴다. 기사 문장을 그대로 옮기지 않는다 (저작권/유사문서 회피).",
        "오리지널 코멘트(내 해석, 경험, 채널 관점) 비중을 전체의 50% 이상으로 유지한다.",
        "네이버 블로그는 3~4문장마다 줄바꿈, 소제목과 이모지를 활용해 모바일 가독성을 높인다.",
        "릴스 Hook은 질문형/반전형/숫자형 중 하나로 첫 3초 안에 궁금증을 만든다."
    ],
    "trend_notes": []
}


# ==========================================================
# 뉴스 수집 (네이버 API + 구글뉴스 RSS + 해외 RSS)
# ==========================================================
def clean_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return (text.replace("&quot;", '"').replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&#39;", "'").strip())


def parse_pub_ts(pub_str):
    """RSS pubDate → unix timestamp (실패 시 None)"""
    try:
        return parsedate_to_datetime(pub_str).timestamp()
    except Exception:
        return None


def fetch_naver_news(cfg, query, display=6):
    cid = cfg.get("naver_client_id", "").strip()
    secret = cfg.get("naver_client_secret", "").strip()
    if not cid or not secret:
        return []
    url = ("https://openapi.naver.com/v1/search/news.json?query="
           + urllib.parse.quote(query) + f"&display={display}&sort=sim")
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", cid)
    req.add_header("X-Naver-Client-Secret", secret)
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read().decode("utf-8"))
    items = []
    for rank, it in enumerate(data.get("items", [])):
        items.append({
            "title": clean_html(it.get("title")),
            "summary": clean_html(it.get("description")),
            "link": it.get("originallink") or it.get("link"),
            "source": "네이버",
            "source_detail": f"네이버검색:{query}",
            "lang": "ko",
            "rank": rank,
            "pub_ts": parse_pub_ts(it.get("pubDate", ""))
        })
    return items


def fetch_google_news(topic, limit=8):
    """구글 뉴스 분야별 RSS (무료, 키 불필요) - 한국판"""
    url = (f"https://news.google.com/rss/headlines/section/topic/{topic}"
           "?hl=ko&gl=KR&ceid=KR:ko")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as res:
        raw = res.read()
    root = ET.fromstring(raw)
    items = []
    for rank, it in enumerate(root.iter("item")):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        press = src_el.text.strip() if (src_el is not None and src_el.text) else "구글뉴스"
        # 구글뉴스 제목은 보통 "제목 - 언론사" 형태 → 언론사 분리
        if " - " in title:
            title = title.rsplit(" - ", 1)[0]
        if title:
            items.append({
                "title": title, "summary": "",
                "link": link, "source": "구글",
                "source_detail": press, "lang": "ko",
                "rank": rank,
                "pub_ts": parse_pub_ts(it.findtext("pubDate") or "")
            })
        if len(items) >= limit:
            break
    return items


def fetch_rss(name, url, limit=6):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as res:
        raw = res.read()
    root = ET.fromstring(raw)
    items = []
    for rank, it in enumerate(root.iter("item")):
        title = (it.findtext("title") or "").strip()
        desc = clean_html(it.findtext("description") or "")[:200]
        link = (it.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "summary": desc,
                          "link": link, "source": "해외",
                          "source_detail": name, "lang": "en",
                          "rank": rank,
                          "pub_ts": parse_pub_ts(it.findtext("pubDate") or "")})
        if len(items) >= limit:
            break
    if not items:  # Atom 형식 대응
        ns = "{http://www.w3.org/2005/Atom}"
        for rank, it in enumerate(root.iter(ns + "entry")):
            title = (it.findtext(ns + "title") or "").strip()
            link_el = it.find(ns + "link")
            link = link_el.get("href") if link_el is not None else ""
            if title:
                items.append({"title": title, "summary": "",
                              "link": link, "source": "해외",
                              "source_detail": name, "lang": "en",
                              "rank": rank, "pub_ts": None})
            if len(items) >= limit:
                break
    return items


def score_fit(item, channel):
    """적합도⭐: 채널 키워드와 매칭 (제목 2점, 요약 1점)"""
    score = 0
    title = item["title"].lower()
    summary = item.get("summary", "").lower()
    for kw in channel.get("keywords", []):
        k = kw.lower()
        if k in title:
            score += 2
        elif k in summary:
            score += 1
    return score


def score_popularity(item):
    """인기도🔥: 랭킹 상위노출(0~10점) + 발행 최신성(0~10점)
    ※ 실제 조회수는 언론사 비공개 → 화제성 근사 지수"""
    score = max(0, 10 - item.get("rank", 10))  # 상위 노출일수록 높음
    ts = item.get("pub_ts")
    if ts:
        hours = max(0, (time.time() - ts) / 3600)
        if hours <= 3:
            score += 10
        elif hours <= 12:
            score += 7
        elif hours <= 24:
            score += 5
        elif hours <= 48:
            score += 3
        else:
            score += 1
    else:
        score += 3  # 시간정보 없으면 중간값
    return score  # 0~20


def ago_text(ts):
    if not ts:
        return "-"
    hours = max(0, (time.time() - ts) / 3600)
    if hours < 1:
        return f"{int(hours*60)}분 전"
    if hours < 24:
        return f"{int(hours)}시간 전"
    return f"{int(hours//24)}일 전"


# ==========================================================
# 무료 이미지 생성 (HF FLUX → Pollinations 자동 전환)
# ==========================================================
def build_image_prompt(topic, channel):
    return (f"A clean, high-quality editorial stock photo representing: {topic}. "
            f"Style: {channel.get('image_style','clean modern photography')}. "
            f"Composition: wide empty negative space on the left side for typography, "
            f"subject positioned on the right. Square 1:1 format. "
            f"Strictly NO text, NO words, NO watermark, NO logos.")


def gen_image_hf(prompt, token, out_path, log):
    url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    payload = json.dumps({
        "inputs": prompt,
        "parameters": {"width": 1024, "height": 1024, "num_inference_steps": 4}
    }).encode("utf-8")
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=120) as res:
                ctype = res.headers.get("Content-Type", "")
                body = res.read()
            if ctype.startswith("image") and len(body) > 10000:
                with open(out_path, "wb") as f:
                    f.write(body)
                return True
            return False
        except urllib.error.HTTPError as e:
            if e.code == 503:
                log("⏳ 허깅페이스 모델 준비 중... 15초 대기")
                time.sleep(15)
                continue
            log(f"⚠ 허깅페이스 응답 {e.code} → 무료 대체 서버로 전환")
            return False
        except Exception as e:
            log(f"⚠ 허깅페이스 오류: {e}")
            return False
    return False


def gen_image_pollinations(prompt, out_path, log):
    url = ("https://image.pollinations.ai/prompt/"
           + urllib.parse.quote(prompt)
           + "?width=1080&height=1080&nologo=true&model=flux")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as res:
            body = res.read()
        if len(body) > 10000:
            with open(out_path, "wb") as f:
                f.write(body)
            return True
        log("⚠ 이미지 응답이 비정상입니다")
        return False
    except Exception as e:
        log(f"⚠ Pollinations 오류: {e}")
        return False


# ==========================================================
# AI 프롬프트 조립 (클로드/ChatGPT/제미나이 공용)
# ==========================================================
def build_ai_prompt(news, channel, guidelines, image_path):
    is_foreign = news.get("lang") == "en"
    g_rules = "\n".join(f"- {r}" for r in guidelines.get("rules", []))
    g_trends = "\n".join(f"- {t}" for t in guidelines.get("trend_notes", [])) or "- (아직 없음)"
    banned = ", ".join(channel.get("banned_words", [])) or "(없음)"

    foreign_block = ""
    if is_foreign:
        foreign_block = f"""
[해외 기사 트리플 검증 절차 - 반드시 순서대로 수행]
이 뉴스는 해외 소스입니다. 본문 작성 전에 아래 3단계를 먼저 수행하고, 각 단계 결과를 간단히 보여주세요.
1차 번역: 제목과 요약을 한국어로 정확히 직역
2차 맥락 최적화: 번역투를 제거하고 한국 독자에게 자연스러운 마케팅 문체로 윤문
3차 교차 검증: 수치·데이터·연구기관명·팩트가 왜곡되거나 누락되지 않았는지 원문과 대조 → "검증 결과: 이상 없음 / 수정사항: ..." 형식으로 보고
※ 원문 전체를 읽어야 정확하다면, 먼저 원문 링크를 웹에서 확인한 뒤 진행해주세요: {news.get('link','')}
"""

    return f"""당신은 SNS 마케팅 콘텐츠 전문가입니다. 아래 뉴스와 채널 정보를 바탕으로 플랫폼별 콘텐츠 세트를 제작해주세요.

[선택된 뉴스]
- 제목: {news['title']}
- 요약: {news.get('summary','(요약 없음)')}
- 출처: {news.get('source_detail', news.get('source',''))}
- 링크: {news.get('link','')}
{foreign_block}
[타겟 채널]
- 채널명: {channel['name']}
- 톤앤매너: {channel['tone']}
- 표현 금지어(법규/과장 방지): {banned}

[시스템 가이드라인 v{guidelines.get('version','1.0')}]
{g_rules}

[최근 트렌드 노트]
{g_trends}

[저작권 안전 원칙 - 최우선]
- 기사 문장을 그대로 복사하지 말 것. 핵심만 요약하고 반드시 출처(매체명)를 명시할 것.
- 전체 분량의 50% 이상은 뉴스가 아닌 '채널 관점의 해석·인사이트·독자 행동 제안'으로 채울 것.

[생성된 배경 이미지 정보]
- 파일: {os.path.basename(image_path) if image_path else '(생성 실패 - 텍스트만 진행)'}
- 구도: 왼쪽에 텍스트용 여백 확보, 피사체는 오른쪽 배치, 1:1 정사각형

=== 아래 3종 세트를 순서대로 출력해주세요 ===

📌 1. 네이버 블로그
- 클릭을 부르는 호기심 자극형 제목 3개 (서로 다른 스타일: 질문형/숫자형/반전형)
- 스토리텔링형 완성 본문 (2,000자 내외, 3~4문장마다 줄바꿈, 소제목 3개 이상, 이모지 활용, 도입부에 공감 훅, 마지막에 댓글 유도 질문)

📌 2. 카드뉴스 5장 가이드 (미리캔버스/캔바 복붙용)
각 장마다 아래 형식으로:
- [N장] 메인 카피 (15자 이내) / 서브 카피 (30자 이내) / 레이아웃 가이드 (텍스트 위치, 폰트 크기 비율, 배경 처리 방법)
- 1장=표지(후킹), 2~4장=핵심 내용, 5장=CTA(팔로우/저장 유도)

📌 3. 인스타그램 릴스
- 첫 3초 Hook 자막 (화면에 크게 뜰 한 줄)
- 15~20초 나레이션 대본 (구어체, 초 단위 타임라인 표시)
- 피드 캡션 (첫 줄 훅 + 본문 + CTA)
- 타겟 해시태그 15개 (대형 5 + 중형 5 + 니치 5)
"""


# ==========================================================
# GUI 앱
# ==========================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("🚀 SNS 트렌드 콘텐츠 스튜디오 v3.0 (무료)")
        root.geometry("960x720")
        root.minsize(820, 600)

        self.cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        self.channels_data = load_json(CHANNELS_PATH, DEFAULT_CHANNELS)
        self.guidelines = load_json(GUIDE_PATH, DEFAULT_GUIDELINES)
        self.history = load_json(HISTORY_PATH, {"used": []})
        self.rss = load_json(RSS_PATH, DEFAULT_RSS)
        os.makedirs(IMG_DIR, exist_ok=True)
        os.makedirs(PROMPT_DIR, exist_ok=True)

        self.news_list = []
        self.busy = False
        self.last_prompt = ""

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_main = ttk.Frame(nb)
        self.tab_set = ttk.Frame(nb)
        nb.add(self.tab_main, text="  📰 콘텐츠 제작  ")
        nb.add(self.tab_set, text="  ⚙ 설정 / API 키  ")

        self._build_main_tab()
        self._build_settings_tab()

        if not self.cfg.get("naver_client_id"):
            self.log("💡 [설정] 탭에서 네이버 API 키를 넣으면 네이버 뉴스도 수집됩니다. (지금은 구글+해외)")

    # ---------------- 메인 탭 ----------------
    def _build_main_tab(self):
        top = ttk.Frame(self.tab_main)
        top.pack(fill="x", padx=10, pady=6)

        ttk.Label(top, text="채널:").pack(side="left")
        self.channel_var = tk.StringVar()
        self.channel_combo = ttk.Combobox(top, textvariable=self.channel_var,
                                          state="readonly", width=20)
        self._refresh_channel_combo()
        self.channel_combo.pack(side="left", padx=(4, 10))
        self.channel_combo.bind("<<ComboboxSelected>>", self._on_channel_change)

        ttk.Label(top, text="분야:").pack(side="left")
        self.cat_var = tk.StringVar(value=list(CATEGORIES.keys())[0])
        self.cat_combo = ttk.Combobox(top, textvariable=self.cat_var,
                                      state="readonly", width=16,
                                      values=list(CATEGORIES.keys()))
        self.cat_combo.pack(side="left", padx=(4, 10))

        ttk.Button(top, text="＋채널", width=6, command=self.add_channel).pack(side="left")
        ttk.Button(top, text="－채널", width=6, command=self.del_channel).pack(side="left", padx=2)

        self.btn_scan = ttk.Button(top, text="🔍 뉴스 스캔 시작", command=self.start_scan)
        self.btn_scan.pack(side="right")

        # 뉴스 목록 (더블클릭=원문 열기)
        mid = ttk.Frame(self.tab_main)
        mid.pack(fill="both", expand=True, padx=10)
        cols = ("src", "fit", "hot", "title", "press", "time")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=13)
        heads = {"src": "출처", "fit": "적합도", "hot": "인기도",
                 "title": "뉴스 제목  (더블클릭=원문 보기)", "press": "매체", "time": "발행"}
        widths = {"src": 56, "fit": 70, "hot": 70, "title": 430, "press": 120, "time": 70}
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c],
                             anchor="center" if c != "title" else "w")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.open_article)

        # 실행 버튼 줄
        btns = ttk.Frame(self.tab_main)
        btns.pack(fill="x", padx=10, pady=6)
        self.btn_make = ttk.Button(btns, text="✨ 콘텐츠 만들기 (이미지+프롬프트)",
                                   command=self.start_make)
        self.btn_make.pack(side="left")
        ttk.Button(btns, text="🌐 원문 보기", command=self.open_article).pack(side="left", padx=4)
        ttk.Button(btns, text="🖼 이미지 폴더",
                   command=lambda: os.startfile(IMG_DIR)).pack(side="left", padx=2)

        # AI 3사 전송 버튼 줄
        ai_row = ttk.LabelFrame(self.tab_main, text=" 🤝 AI에게 던지기 (프롬프트 복사 + 사이트 자동 열림 → Ctrl+V만 하세요) ")
        ai_row.pack(fill="x", padx=10, pady=(0, 4))
        for name in AI_SITES:
            icon = {"클로드": "🟠", "ChatGPT": "🟢", "제미나이": "🔵"}[name]
            ttk.Button(ai_row, text=f"{icon} {name}에게 던지기",
                       command=lambda n=name: self.throw_to_ai(n)).pack(side="left", padx=6, pady=5)
        ttk.Button(ai_row, text="📋 복사만", command=self.recopy).pack(side="left", padx=6)

        ttk.Label(self.tab_main, text="진행 상황:").pack(anchor="w", padx=10)
        self.log_box = tk.Text(self.tab_main, height=8, state="disabled",
                               bg="#1e1e1e", fg="#d4d4d4", font=("맑은 고딕", 9))
        self.log_box.pack(fill="both", padx=10, pady=(0, 10))

    # ---------------- 설정 탭 ----------------
    def _build_settings_tab(self):
        frm = ttk.LabelFrame(self.tab_set, text=" 네이버 검색 API (무료, 네이버 뉴스용) ")
        frm.pack(fill="x", padx=12, pady=10)
        ttk.Label(frm, text="발급: developers.naver.com/apps → 애플리케이션 등록 → 검색 API → WEB(http://localhost)",
                  foreground="gray").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Label(frm, text="Client ID:").grid(row=1, column=0, sticky="e", padx=8, pady=4)
        self.ent_id = ttk.Entry(frm, width=52)
        self.ent_id.insert(0, self.cfg.get("naver_client_id", ""))
        self.ent_id.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(frm, text="Client Secret:").grid(row=2, column=0, sticky="e", padx=8, pady=4)
        self.ent_secret = ttk.Entry(frm, width=52)
        self.ent_secret.insert(0, self.cfg.get("naver_client_secret", ""))
        self.ent_secret.grid(row=2, column=1, sticky="w", pady=4)

        frm2 = ttk.LabelFrame(self.tab_set, text=" 허깅페이스 토큰 (선택 - 비워두면 무료 대체 서버 사용) ")
        frm2.pack(fill="x", padx=12, pady=10)
        ttk.Label(frm2, text="Token:").grid(row=0, column=0, sticky="e", padx=8, pady=4)
        self.ent_hf = ttk.Entry(frm2, width=52)
        self.ent_hf.insert(0, self.cfg.get("hf_token", ""))
        self.ent_hf.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Button(self.tab_set, text="💾 설정 저장", command=self.save_settings).pack(pady=6)

        frm3 = ttk.LabelFrame(self.tab_set, text=" 🔄 알고리즘 업데이트 (트렌드/규칙 학습 → 판올림) ")
        frm3.pack(fill="x", padx=12, pady=10)
        ttk.Label(frm3, text="예: 요즘 릴스는 3초 안에 결론부터 말하는 게 대세",
                  foreground="gray").pack(anchor="w", padx=8)
        row = ttk.Frame(frm3)
        row.pack(fill="x", padx=8, pady=6)
        self.ent_update = ttk.Entry(row)
        self.ent_update.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="판올림 적용", command=self.apply_update).pack(side="left", padx=6)
        self.lbl_ver = ttk.Label(frm3, text=f"현재 가이드라인 버전: v{self.guidelines.get('version','1.0')}")
        self.lbl_ver.pack(anchor="w", padx=8, pady=(0, 6))

        frm4 = ttk.LabelFrame(self.tab_set, text=" ℹ 인기도🔥 지수 안내 ")
        frm4.pack(fill="x", padx=12, pady=10)
        ttk.Label(frm4, text="실제 조회수는 언론사가 공개하지 않아 무료로 수집이 불가능합니다.\n"
                             "대신 [뉴스 랭킹 상위노출 + 발행 최신성]을 결합한 화제성 지수로 표시합니다. (🔥 많을수록 핫함)",
                  foreground="gray", justify="left").pack(anchor="w", padx=8, pady=4)

    # ---------------- 공통 ----------------
    def log(self, msg):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"{datetime.now().strftime('%H:%M:%S')}  {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _do)

    def _refresh_channel_combo(self):
        names = [c["name"] for c in self.channels_data["channels"]]
        self.channel_combo["values"] = names
        if names and self.channel_var.get() not in names:
            self.channel_var.set(names[0])

    def _on_channel_change(self, event=None):
        ch = self.current_channel()
        if ch and ch.get("default_category") in CATEGORIES:
            self.cat_var.set(ch["default_category"])

    def current_channel(self):
        name = self.channel_var.get()
        for c in self.channels_data["channels"]:
            if c["name"] == name:
                return c
        return None

    def selected_news(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.news_list[int(sel[0])]

    # ---------------- 채널 관리 ----------------
    def add_channel(self):
        name = simpledialog.askstring("채널 추가", "새 채널 이름:", parent=self.root)
        if not name:
            return
        tone = simpledialog.askstring("채널 추가", "톤앤매너 설명:", parent=self.root) or ""
        kw = simpledialog.askstring("채널 추가", "핵심 키워드 (쉼표로 구분):", parent=self.root) or ""
        nq = simpledialog.askstring("채널 추가", "네이버 검색어 (쉼표로 구분):", parent=self.root) or name
        img = simpledialog.askstring("채널 추가", "이미지 분위기 (영어):",
                                     parent=self.root) or "clean modern photography"
        self.channels_data["channels"].append({
            "name": name, "tone": tone,
            "keywords": [k.strip() for k in kw.split(",") if k.strip()],
            "image_style": img, "banned_words": [],
            "naver_queries": [q.strip() for q in nq.split(",") if q.strip()],
            "default_category": "☕ 라이프스타일",
            "rss_categories": ["lifestyle"]
        })
        save_json(CHANNELS_PATH, self.channels_data)
        self._refresh_channel_combo()
        self.channel_var.set(name)
        self.log(f"✅ 채널 '{name}' 추가 완료")

    def del_channel(self):
        ch = self.current_channel()
        if not ch:
            return
        if messagebox.askyesno("채널 삭제", f"'{ch['name']}' 채널을 삭제할까요?"):
            self.channels_data["channels"].remove(ch)
            save_json(CHANNELS_PATH, self.channels_data)
            self._refresh_channel_combo()
            self.log("🗑 채널 삭제 완료")

    # ---------------- 설정/판올림 ----------------
    def save_settings(self):
        self.cfg["naver_client_id"] = self.ent_id.get().strip()
        self.cfg["naver_client_secret"] = self.ent_secret.get().strip()
        self.cfg["hf_token"] = self.ent_hf.get().strip()
        save_json(CONFIG_PATH, self.cfg)
        messagebox.showinfo("저장 완료", "설정이 저장되었습니다!")
        self.log("💾 설정 저장 완료")

    def apply_update(self):
        note = self.ent_update.get().strip()
        if not note:
            return
        self.guidelines["trend_notes"].append(
            f"{datetime.now().strftime('%Y-%m-%d')} | {note}")
        try:
            major, minor = self.guidelines.get("version", "1.0").split(".")
            self.guidelines["version"] = f"{major}.{int(minor)+1}"
        except Exception:
            self.guidelines["version"] = "1.1"
        self.guidelines["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_json(GUIDE_PATH, self.guidelines)
        self.lbl_ver.config(text=f"현재 가이드라인 버전: v{self.guidelines['version']}")
        self.ent_update.delete(0, "end")
        self.log(f"🔄 가이드라인 v{self.guidelines['version']} 판올림 완료")

    # ---------------- 뉴스 스캔 ----------------
    def start_scan(self):
        if self.busy:
            return
        ch = self.current_channel()
        if not ch:
            messagebox.showwarning("알림", "채널을 먼저 선택하세요.")
            return
        self.busy = True
        self.btn_scan.config(state="disabled")
        threading.Thread(target=self._scan_worker,
                         args=(ch, self.cat_var.get()), daemon=True).start()

    def _scan_worker(self, ch, cat_name):
        try:
            cat = CATEGORIES.get(cat_name, CATEGORIES["🎯 채널 맞춤(자동)"])
            self.log(f"🔍 [{ch['name']}] × [{cat_name}] 스캔 시작...")
            used_titles = {h["title"] for h in self.history.get("used", [])}
            all_items = []
            n = self.cfg.get("news_per_source", 6)

            # 네이버 (분야 지정 시 분야 검색어, 아니면 채널 검색어)
            naver_queries = cat["naver"] if cat["naver"] else ch.get("naver_queries", [])
            for q in naver_queries:
                try:
                    got = fetch_naver_news(self.cfg, q, display=n)
                    if got:
                        self.log(f"  🇳 네이버 '{q}' → {len(got)}건")
                    all_items += got
                except Exception as e:
                    self.log(f"  ⚠ 네이버 '{q}' 오류: {e}")

            # 구글 뉴스 (분야 토픽)
            g_topic = cat["google"]
            if not g_topic and cat_name.startswith("🎯"):
                # 채널 맞춤이면 채널 기본 분야의 구글 토픽 사용
                default_cat = CATEGORIES.get(ch.get("default_category", ""), {})
                g_topic = default_cat.get("google")
            if g_topic:
                try:
                    got = fetch_google_news(g_topic, limit=n + 2)
                    self.log(f"  🇬 구글뉴스({g_topic}) → {len(got)}건")
                    all_items += got
                except Exception as e:
                    self.log(f"  ⚠ 구글뉴스 오류: {e}")

            # 해외 RSS
            rss_cat = cat["rss"]
            rss_cats = [rss_cat] if rss_cat else (ch.get("rss_categories", []) if cat_name.startswith("🎯") else [])
            for rc in rss_cats:
                for src in self.rss.get(rc, []):
                    try:
                        got = fetch_rss(src["name"], src["url"], limit=n)
                        self.log(f"  🌏 {src['name']} → {len(got)}건")
                        all_items += got
                    except Exception as e:
                        self.log(f"  ⚠ {src['name']} 오류: {e}")

            # 중복/기사용 제거 + 점수 계산
            seen, filtered = set(), []
            for it in all_items:
                key = it["title"][:40]
                if key in seen or it["title"] in used_titles:
                    continue
                seen.add(key)
                it["fit"] = score_fit(it, ch)
                it["hot"] = score_popularity(it)
                filtered.append(it)
            # 정렬: 적합도 우선, 동점이면 인기도
            filtered.sort(key=lambda x: (x["fit"], x["hot"]), reverse=True)
            self.news_list = filtered[:20]

            def _fill():
                self.tree.delete(*self.tree.get_children())
                for i, nitem in enumerate(self.news_list):
                    src_icon = {"네이버": "🇳", "구글": "🇬", "해외": "🌏"}.get(nitem["source"], "")
                    stars = "⭐" * min(max(nitem["fit"] // 2, 0), 5) or "·"
                    fires = "🔥" * min(max(nitem["hot"] // 4, 0), 5) or "·"
                    self.tree.insert("", "end", iid=str(i), values=(
                        f"{src_icon}{nitem['source']}", stars, fires,
                        nitem["title"], nitem.get("source_detail", ""),
                        ago_text(nitem.get("pub_ts"))))
            self.root.after(0, _fill)
            self.log(f"✅ 스캔 완료! {len(self.news_list)}건 (적합도⭐→인기도🔥 순 정렬)")
            self.log("👉 뉴스 클릭 후 [✨ 콘텐츠 만들기] / 더블클릭하면 원문이 열립니다")
        finally:
            self.busy = False
            self.root.after(0, lambda: self.btn_scan.config(state="normal"))

    # ---------------- 원문 열기 ----------------
    def open_article(self, event=None):
        news = self.selected_news()
        if not news:
            messagebox.showinfo("알림", "목록에서 뉴스를 먼저 선택하세요.")
            return
        link = news.get("link", "")
        if link:
            webbrowser.open(link)
            self.log(f"🌐 원문 열기: {news['title'][:40]}")
        else:
            messagebox.showinfo("알림", "이 뉴스는 링크 정보가 없습니다.")

    # ---------------- 콘텐츠 생성 ----------------
    def start_make(self):
        if self.busy:
            return
        news = self.selected_news()
        if not news:
            messagebox.showwarning("알림", "목록에서 뉴스를 먼저 클릭해서 선택하세요.")
            return
        ch = self.current_channel()
        self.busy = True
        self.btn_make.config(state="disabled")
        threading.Thread(target=self._make_worker, args=(news, ch), daemon=True).start()

    def _make_worker(self, news, ch):
        try:
            self.log(f"✅ 채택: {news['title'][:50]}")
            if news["lang"] == "en":
                self.log("🌏 해외 기사 → 트리플 검증 절차 포함")

            self.log("🎨 배경 이미지 생성 중... (10~60초)")
            prompt_img = build_image_prompt(news["title"], ch)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            img_path = os.path.join(IMG_DIR, f"card_bg_{ts}.png")
            ok = False
            token = self.cfg.get("hf_token", "").strip()
            if token:
                self.log("  → 허깅페이스 FLUX 시도...")
                ok = gen_image_hf(prompt_img, token, img_path, self.log)
            if not ok:
                self.log("  → Pollinations 무료 서버 사용...")
                ok = gen_image_pollinations(prompt_img, img_path, self.log)
            if ok:
                self.log(f"  💾 저장: images/{os.path.basename(img_path)}")
            else:
                img_path = None
                self.log("  ❌ 이미지 실패 (프롬프트만 진행)")

            prompt = build_ai_prompt(news, ch, self.guidelines, img_path)
            self.last_prompt = prompt
            with open(os.path.join(PROMPT_DIR, f"prompt_{ts}.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

            def _copy():
                self.root.clipboard_clear()
                self.root.clipboard_append(prompt)
            self.root.after(0, _copy)

            self.history["used"].append({
                "title": news["title"], "link": news.get("link", ""),
                "channel": ch["name"],
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_json(HISTORY_PATH, self.history)

            self.log("=" * 46)
            self.log("🎉 완료! 프롬프트 클립보드 복사됨")
            self.log("👉 아래 [AI에게 던지기] 버튼을 누르면 사이트가 열립니다 → Ctrl+V")
            self.log("=" * 46)
        finally:
            self.busy = False
            self.root.after(0, lambda: self.btn_make.config(state="normal"))

    # ---------------- AI에게 던지기 ----------------
    def throw_to_ai(self, ai_name):
        if not self.last_prompt:
            messagebox.showinfo("알림", "먼저 [✨ 콘텐츠 만들기]로 프롬프트를 생성하세요.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_prompt)
        webbrowser.open(AI_SITES[ai_name])
        self.log(f"🚀 {ai_name} 사이트 열림 + 프롬프트 복사 완료 → 채팅창에 Ctrl+V 하세요!")

    def recopy(self):
        if not self.last_prompt:
            messagebox.showinfo("알림", "아직 생성된 프롬프트가 없습니다.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_prompt)
        self.log("📋 프롬프트 복사 완료")


if __name__ == "__main__":
    root = tk.Tk()
    try:
        from tkinter import font
        font.nametofont("TkDefaultFont").configure(family="맑은 고딕", size=10)
    except Exception:
        pass
    App(root)
    root.mainloop()
