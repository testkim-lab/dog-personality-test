# -*- coding: utf-8 -*-
"""
============================================================
 SNS 트렌드 콘텐츠 스튜디오 v2.0  (GUI 앱 버전, 100% 무료)
============================================================
 - 더블클릭으로 실행되는 창(App) 형태
 - 추가 라이브러리 설치 불필요 (파이썬 기본 기능만 사용)
 - 다른 컴퓨터 설치법: ① python.org 에서 파이썬 설치
   (설치 시 "Add python.exe to PATH" 체크!) ② 이 파일 복사 ③ 더블클릭
 - 설정/채널/기록 파일은 이 파일과 같은 폴더에 자동 생성됩니다
============================================================
"""
import os
import re
import json
import time
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

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
    "news_per_source": 5
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
            "rss_categories": ["health"]
        },
        {
            "name": "개인 일상 계정",
            "tone": "친근하고 공감 가며, 일상 속 인사이트를 나누는 따뜻한 소통형 톤",
            "keywords": ["일상", "라이프", "트렌드", "심리", "습관", "자기계발", "MZ", "직장", "취미", "여행", "lifestyle", "trend", "habit"],
            "image_style": "Warm, cozy, friendly lifestyle, modern and natural daily routine ambiance",
            "banned_words": [],
            "naver_queries": ["라이프스타일 트렌드", "MZ세대 일상", "요즘 유행"],
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
# 뉴스 수집 (네이버 API + 해외 RSS) - urllib만 사용
# ==========================================================
def clean_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return (text.replace("&quot;", '"').replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&#39;", "'").strip())


def fetch_naver_news(cfg, query, display=5):
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
    for it in data.get("items", []):
        items.append({
            "title": clean_html(it.get("title")),
            "summary": clean_html(it.get("description")),
            "link": it.get("originallink") or it.get("link"),
            "source": f"네이버뉴스:{query}",
            "lang": "ko"
        })
    return items


def fetch_rss(name, url, limit=5):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as res:
        raw = res.read()
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        desc = clean_html(it.findtext("description") or "")[:200]
        link = (it.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "summary": desc,
                          "link": link, "source": name, "lang": "en"})
        if len(items) >= limit:
            break
    if not items:  # Atom 형식 대응
        ns = "{http://www.w3.org/2005/Atom}"
        for it in root.iter(ns + "entry"):
            title = (it.findtext(ns + "title") or "").strip()
            link_el = it.find(ns + "link")
            link = link_el.get("href") if link_el is not None else ""
            if title:
                items.append({"title": title, "summary": "",
                              "link": link, "source": name, "lang": "en"})
            if len(items) >= limit:
                break
    return items


def score_news(item, channel):
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
# 클로드 프롬프트 조립
# ==========================================================
def build_claude_prompt(news, channel, guidelines, image_path):
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
- 출처: {news['source']}
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
        root.title("🚀 SNS 트렌드 콘텐츠 스튜디오 v2.0 (무료)")
        root.geometry("860x680")
        root.minsize(760, 560)

        # 데이터 로드
        self.cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        self.channels_data = load_json(CHANNELS_PATH, DEFAULT_CHANNELS)
        self.guidelines = load_json(GUIDE_PATH, DEFAULT_GUIDELINES)
        self.history = load_json(HISTORY_PATH, {"used": []})
        self.rss = load_json(RSS_PATH, DEFAULT_RSS)
        os.makedirs(IMG_DIR, exist_ok=True)
        os.makedirs(PROMPT_DIR, exist_ok=True)

        self.news_list = []
        self.busy = False

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_main = ttk.Frame(nb)
        self.tab_set = ttk.Frame(nb)
        nb.add(self.tab_main, text="  📰 콘텐츠 제작  ")
        nb.add(self.tab_set, text="  ⚙ 설정 / API 키  ")

        self._build_main_tab()
        self._build_settings_tab()

        if not self.cfg.get("naver_client_id"):
            self.log("💡 [설정] 탭에서 네이버 API 키를 넣으면 국내 뉴스도 수집됩니다. (지금은 해외 뉴스만)")

    # ---------------- 메인 탭 ----------------
    def _build_main_tab(self):
        top = ttk.Frame(self.tab_main)
        top.pack(fill="x", padx=10, pady=8)

        ttk.Label(top, text="채널:").pack(side="left")
        self.channel_var = tk.StringVar()
        self.channel_combo = ttk.Combobox(top, textvariable=self.channel_var,
                                          state="readonly", width=28)
        self._refresh_channel_combo()
        self.channel_combo.pack(side="left", padx=6)

        ttk.Button(top, text="＋ 채널 추가", command=self.add_channel).pack(side="left", padx=2)
        ttk.Button(top, text="－ 채널 삭제", command=self.del_channel).pack(side="left", padx=2)

        self.btn_scan = ttk.Button(top, text="🔍 뉴스 스캔 시작", command=self.start_scan)
        self.btn_scan.pack(side="right", padx=2)

        # 뉴스 목록
        mid = ttk.Frame(self.tab_main)
        mid.pack(fill="both", expand=True, padx=10)
        cols = ("flag", "score", "title", "source")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=12)
        self.tree.heading("flag", text="구분")
        self.tree.heading("score", text="적합도")
        self.tree.heading("title", text="뉴스 제목")
        self.tree.heading("source", text="출처")
        self.tree.column("flag", width=52, anchor="center")
        self.tree.column("score", width=64, anchor="center")
        self.tree.column("title", width=470)
        self.tree.column("source", width=150)
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 실행 버튼들
        btns = ttk.Frame(self.tab_main)
        btns.pack(fill="x", padx=10, pady=6)
        self.btn_make = ttk.Button(btns, text="✨ 선택한 뉴스로 콘텐츠 만들기 (이미지+프롬프트)",
                                   command=self.start_make)
        self.btn_make.pack(side="left")
        ttk.Button(btns, text="📋 프롬프트 다시 복사", command=self.recopy).pack(side="left", padx=6)
        ttk.Button(btns, text="🖼 이미지 폴더 열기",
                   command=lambda: os.startfile(IMG_DIR)).pack(side="left", padx=2)

        # 진행 상황 로그
        ttk.Label(self.tab_main, text="진행 상황:").pack(anchor="w", padx=10)
        self.log_box = tk.Text(self.tab_main, height=9, state="disabled",
                               bg="#1e1e1e", fg="#d4d4d4", font=("맑은 고딕", 9))
        self.log_box.pack(fill="both", padx=10, pady=(0, 10))
        self.last_prompt = ""

    # ---------------- 설정 탭 ----------------
    def _build_settings_tab(self):
        frm = ttk.LabelFrame(self.tab_set, text=" 네이버 검색 API (무료, 국내 뉴스용) ")
        frm.pack(fill="x", padx=12, pady=10)
        ttk.Label(frm, text="발급: developers.naver.com/apps → 애플리케이션 등록 → 검색 API → WEB(http://localhost)",
                  foreground="gray").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Label(frm, text="Client ID:").grid(row=1, column=0, sticky="e", padx=8, pady=4)
        self.ent_id = ttk.Entry(frm, width=50)
        self.ent_id.insert(0, self.cfg.get("naver_client_id", ""))
        self.ent_id.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(frm, text="Client Secret:").grid(row=2, column=0, sticky="e", padx=8, pady=4)
        self.ent_secret = ttk.Entry(frm, width=50)
        self.ent_secret.insert(0, self.cfg.get("naver_client_secret", ""))
        self.ent_secret.grid(row=2, column=1, sticky="w", pady=4)

        frm2 = ttk.LabelFrame(self.tab_set, text=" 허깅페이스 토큰 (선택사항 - 비워두면 무료 대체 서버 사용) ")
        frm2.pack(fill="x", padx=12, pady=10)
        ttk.Label(frm2, text="Token:").grid(row=0, column=0, sticky="e", padx=8, pady=4)
        self.ent_hf = ttk.Entry(frm2, width=50)
        self.ent_hf.insert(0, self.cfg.get("hf_token", ""))
        self.ent_hf.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Button(self.tab_set, text="💾 설정 저장", command=self.save_settings).pack(pady=6)

        frm3 = ttk.LabelFrame(self.tab_set, text=" 🔄 알고리즘 업데이트 (트렌드/규칙을 시스템에 학습시키기) ")
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

    # ---------------- 공통 유틸 ----------------
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

    def current_channel(self):
        name = self.channel_var.get()
        for c in self.channels_data["channels"]:
            if c["name"] == name:
                return c
        return None

    # ---------------- 채널 관리 ----------------
    def add_channel(self):
        name = simpledialog.askstring("채널 추가", "새 채널 이름:", parent=self.root)
        if not name:
            return
        tone = simpledialog.askstring("채널 추가", "톤앤매너 설명:", parent=self.root) or ""
        kw = simpledialog.askstring("채널 추가", "핵심 키워드 (쉼표로 구분):", parent=self.root) or ""
        nq = simpledialog.askstring("채널 추가", "네이버 검색어 (쉼표로 구분):", parent=self.root) or name
        img = simpledialog.askstring("채널 추가", "이미지 분위기 (영어, 예: warm minimal mood):",
                                     parent=self.root) or "clean modern photography"
        self.channels_data["channels"].append({
            "name": name, "tone": tone,
            "keywords": [k.strip() for k in kw.split(",") if k.strip()],
            "image_style": img, "banned_words": [],
            "naver_queries": [q.strip() for q in nq.split(",") if q.strip()],
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
            self.log(f"🗑 채널 삭제 완료")

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
        self.log(f"🔄 가이드라인 v{self.guidelines['version']} 판올림 완료 (다음 프롬프트부터 반영)")

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
        threading.Thread(target=self._scan_worker, args=(ch,), daemon=True).start()

    def _scan_worker(self, ch):
        try:
            self.log(f"🔍 '{ch['name']}' 뉴스 스캔 시작...")
            used_titles = {h["title"] for h in self.history.get("used", [])}
            all_items = []
            n = self.cfg.get("news_per_source", 5)

            for q in ch.get("naver_queries", []):
                try:
                    got = fetch_naver_news(self.cfg, q, display=n)
                    if got:
                        self.log(f"  🇰🇷 네이버 '{q}' → {len(got)}건")
                    all_items += got
                except Exception as e:
                    self.log(f"  ⚠ 네이버 '{q}' 오류: {e}")

            for cat in ch.get("rss_categories", []):
                for src in self.rss.get(cat, []):
                    try:
                        got = fetch_rss(src["name"], src["url"], limit=n)
                        self.log(f"  🌏 {src['name']} → {len(got)}건")
                        all_items += got
                    except Exception as e:
                        self.log(f"  ⚠ {src['name']} 오류: {e}")

            seen, filtered = set(), []
            for it in all_items:
                key = it["title"][:40]
                if key in seen or it["title"] in used_titles:
                    continue
                seen.add(key)
                it["score"] = score_news(it, ch)
                filtered.append(it)
            filtered.sort(key=lambda x: x["score"], reverse=True)
            self.news_list = filtered[:15]

            def _fill():
                self.tree.delete(*self.tree.get_children())
                for i, nitem in enumerate(self.news_list):
                    flag = "🌏" if nitem["lang"] == "en" else "🇰🇷"
                    stars = "⭐" * min(nitem["score"], 5)
                    self.tree.insert("", "end", iid=str(i),
                                     values=(flag, stars, nitem["title"], nitem["source"]))
            self.root.after(0, _fill)
            self.log(f"✅ 스캔 완료! 적합도순 {len(self.news_list)}건 (목록에서 뉴스를 클릭해 선택하세요)")
        finally:
            self.busy = False
            self.root.after(0, lambda: self.btn_scan.config(state="normal"))

    # ---------------- 콘텐츠 생성 ----------------
    def start_make(self):
        if self.busy:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("알림", "목록에서 뉴스를 먼저 클릭해서 선택하세요.")
            return
        news = self.news_list[int(sel[0])]
        ch = self.current_channel()
        self.busy = True
        self.btn_make.config(state="disabled")
        threading.Thread(target=self._make_worker, args=(news, ch), daemon=True).start()

    def _make_worker(self, news, ch):
        try:
            self.log(f"✅ 채택: {news['title'][:50]}")
            if news["lang"] == "en":
                self.log("🌏 해외 기사 → 트리플 검증(번역→윤문→교차검증) 절차 포함됩니다")

            # 이미지 생성
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
                self.log(f"  💾 이미지 저장: images 폴더 → {os.path.basename(img_path)}")
            else:
                img_path = None
                self.log("  ❌ 이미지 생성 실패 (프롬프트만 진행합니다)")

            # 프롬프트 조립 + 클립보드 복사
            prompt = build_claude_prompt(news, ch, self.guidelines, img_path)
            self.last_prompt = prompt
            txt_path = os.path.join(PROMPT_DIR, f"claude_prompt_{ts}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(prompt)

            def _copy():
                self.root.clipboard_clear()
                self.root.clipboard_append(prompt)
            self.root.after(0, _copy)

            # 히스토리 기록
            self.history["used"].append({
                "title": news["title"], "link": news.get("link", ""),
                "channel": ch["name"],
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_json(HISTORY_PATH, self.history)

            self.log("=" * 46)
            self.log("🎉 완료! 클립보드에 프롬프트가 복사되었습니다")
            self.log("👉 클로드 앱을 열고 Ctrl+V → Enter 하세요!")
            self.log("=" * 46)
            self.root.after(0, lambda: messagebox.showinfo(
                "완료!",
                "프롬프트가 클립보드에 복사되었습니다!\n\n"
                "1) 클로드 앱을 열고 Ctrl+V → 전송\n"
                "2) 배경 이미지는 [이미지 폴더 열기] 버튼으로 확인\n"
                "3) 미리캔버스/캔바에서 조합 후 발행"))
        finally:
            self.busy = False
            self.root.after(0, lambda: self.btn_make.config(state="normal"))

    def recopy(self):
        if not self.last_prompt:
            messagebox.showinfo("알림", "아직 생성된 프롬프트가 없습니다.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_prompt)
        self.log("📋 프롬프트를 클립보드에 다시 복사했습니다")


if __name__ == "__main__":
    root = tk.Tk()
    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(family="맑은 고딕", size=10)
    except Exception:
        pass
    App(root)
    root.mainloop()
