# -*- coding: utf-8 -*-
"""
============================================================
 SNS 트렌드 콘텐츠 반자동화 시스템 v1.0 (100% 무료 구조)
============================================================
 [기능]
 1. 채널 관리   : channels.json 에서 채널 자유 추가/수정/삭제
 2. 뉴스 수집   : 네이버 검색 API(국내) + 해외 RSS (모두 무료)
 3. 적합도 정렬 : 채널 키워드와 매칭 점수로 뉴스 정렬
 4. 중복 방지   : 이미 사용한 뉴스는 history.json 에 기록·제외
 5. 이미지 생성 : HuggingFace FLUX(무료 크레딧) → 실패 시
                  Pollinations(키 불필요, 무제한 무료) 자동 전환
 6. 프롬프트    : 해외기사 트리플검증 + 플랫폼별 원고 요청을
                  하나의 완성 프롬프트로 조립 → 클립보드 복사
 7. 자가 판올림 : "[알고리즘 업데이트]: ..." 입력 시
                  guidelines.json 에 버전 기록·다음 프롬프트에 반영

 [필요 라이브러리]  pip install requests pyperclip
 (pyperclip 이 없으면 프롬프트를 txt 파일로 저장해줍니다)

 [네이버 API 키 무료 발급 - 5분]
  1) https://developers.naver.com/apps  접속 → 네이버 로그인
  2) [애플리케이션 등록] → 이름 아무거나 → 사용 API: "검색" 체크
  3) 환경: WEB 설정 → http://localhost 입력 → 등록
  4) 발급된 Client ID / Client Secret 을 config.json 에 입력
     (첫 실행 시 config.json 이 자동 생성됩니다)
============================================================
"""
import os
import re
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

try:
    import requests
except ImportError:
    print("requests 라이브러리가 필요합니다:  pip install requests")
    raise SystemExit

try:
    import pyperclip
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CHANNELS_PATH = os.path.join(BASE_DIR, "channels.json")
GUIDE_PATH = os.path.join(BASE_DIR, "guidelines.json")
HISTORY_PATH = os.path.join(BASE_DIR, "history.json")
IMG_DIR = os.path.join(BASE_DIR, "images")
PROMPT_DIR = os.path.join(BASE_DIR, "prompts")


# ==========================================================
# 0. 설정 파일 로드/초기화
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
    "naver_client_id": "여기에_클라이언트_ID_입력",
    "naver_client_secret": "여기에_시크릿_입력",
    "hf_token": "",  # 비워두면 Pollinations(무료)만 사용
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

# 해외 무료 RSS 소스 (카테고리별) - 자유롭게 추가/수정 가능
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


def load_all_configs():
    cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    ch = load_json(CHANNELS_PATH, DEFAULT_CHANNELS)
    gd = load_json(GUIDE_PATH, DEFAULT_GUIDELINES)
    hist = load_json(HISTORY_PATH, {"used": []})
    rss_path = os.path.join(BASE_DIR, "rss_sources.json")
    rss = load_json(rss_path, DEFAULT_RSS)
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(PROMPT_DIR, exist_ok=True)
    return cfg, ch, gd, hist, rss


# ==========================================================
# 1. 채널 관리 (동적 선택 + 추가/삭제)
# ==========================================================
def manage_channels(channels_data):
    while True:
        print("\n" + "=" * 50)
        print("📺 등록된 채널 목록")
        print("=" * 50)
        for i, c in enumerate(channels_data["channels"], 1):
            print(f"  {i}. {c['name']}")
        print("-" * 50)
        print("  번호 입력 = 채널 선택 | a = 채널 추가 | d = 채널 삭제")
        sel = input("> ").strip().lower()

        if sel == "a":
            name = input("  새 채널 이름: ").strip()
            tone = input("  톤앤매너 설명: ").strip()
            kw = input("  핵심 키워드 (쉼표로 구분): ").strip()
            img = input("  이미지 분위기 (영어, 예: warm minimal café mood): ").strip()
            nq = input("  네이버 검색어 (쉼표로 구분, 예: 카페 트렌드,디저트): ").strip()
            channels_data["channels"].append({
                "name": name, "tone": tone,
                "keywords": [k.strip() for k in kw.split(",") if k.strip()],
                "image_style": img or "clean modern photography",
                "banned_words": [],
                "naver_queries": [q.strip() for q in nq.split(",") if q.strip()],
                "rss_categories": ["lifestyle"]
            })
            save_json(CHANNELS_PATH, channels_data)
            print("  ✅ 채널이 추가되었습니다.")
        elif sel == "d":
            n = input("  삭제할 채널 번호: ").strip()
            if n.isdigit() and 1 <= int(n) <= len(channels_data["channels"]):
                removed = channels_data["channels"].pop(int(n) - 1)
                save_json(CHANNELS_PATH, channels_data)
                print(f"  🗑 '{removed['name']}' 삭제 완료.")
        elif sel.isdigit() and 1 <= int(sel) <= len(channels_data["channels"]):
            return channels_data["channels"][int(sel) - 1]
        else:
            print("  ⚠ 올바른 입력이 아닙니다.")


# ==========================================================
# 2. 뉴스 수집 (네이버 API + 해외 RSS)
# ==========================================================
def clean_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return (text.replace("&quot;", '"').replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&#39;", "'").strip())


def fetch_naver_news(cfg, query, display=5):
    cid, secret = cfg.get("naver_client_id", ""), cfg.get("naver_client_secret", "")
    if not cid or "입력" in cid:
        return []
    url = ("https://openapi.naver.com/v1/search/news.json?query="
           + urllib.parse.quote(query) + f"&display={display}&sort=sim")
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", cid)
    req.add_header("X-Naver-Client-Secret", secret)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))
        items = []
        for it in data.get("items", []):
            items.append({
                "title": clean_html(it.get("title")),
                "summary": clean_html(it.get("description")),
                "link": it.get("originallink") or it.get("link"),
                "source": f"네이버뉴스 검색:{query}",
                "lang": "ko"
            })
        return items
    except Exception as e:
        print(f"  ⚠ 네이버 API 오류({query}): {e}")
        return []


def fetch_rss(name, url, limit=5):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as res:
            raw = res.read()
        root = ET.fromstring(raw)
        items = []
        # RSS 2.0
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            desc = clean_html(it.findtext("description") or "")[:200]
            link = (it.findtext("link") or "").strip()
            if title:
                items.append({"title": title, "summary": desc,
                              "link": link, "source": name, "lang": "en"})
            if len(items) >= limit:
                break
        # Atom 형식 대응
        if not items:
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
    except Exception as e:
        print(f"  ⚠ RSS 오류({name}): {e}")
        return []


def score_news(item, channel):
    """채널 키워드와의 매칭 점수 (제목 가중치 2배)"""
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


def collect_news(cfg, channel, rss_sources, history):
    print("\n🔍 [Step 1] 실시간 뉴스 스캔 중... (네이버 + 해외 RSS)")
    used_titles = {h["title"] for h in history.get("used", [])}
    all_items = []

    n = cfg.get("news_per_source", 5)
    for q in channel.get("naver_queries", []):
        all_items += fetch_naver_news(cfg, q, display=n)

    for cat in channel.get("rss_categories", []):
        for src in rss_sources.get(cat, []):
            all_items += fetch_rss(src["name"], src["url"], limit=n)

    # 중복(제목 기준) 및 과거 사용분 제거
    seen, filtered = set(), []
    for it in all_items:
        key = it["title"][:40]
        if key in seen or it["title"] in used_titles:
            continue
        seen.add(key)
        it["score"] = score_news(it, channel)
        filtered.append(it)

    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered[:12]


# ==========================================================
# 3. 무료 이미지 생성 (HF FLUX → Pollinations 자동 전환)
# ==========================================================
def build_image_prompt(topic, channel):
    return (f"A clean, high-quality editorial stock photo representing: {topic}. "
            f"Style: {channel.get('image_style','clean modern photography')}. "
            f"Composition: wide empty negative space on the left side for typography, "
            f"subject positioned on the right. Square 1:1 format. "
            f"Strictly NO text, NO words, NO watermark, NO logos.")


def gen_image_hf(prompt, token, out_path):
    url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"inputs": prompt,
               "parameters": {"width": 1024, "height": 1024, "num_inference_steps": 4}}
    for attempt in range(2):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with open(out_path, "wb") as f:
                    f.write(r.content)
                return True
            if r.status_code == 503:
                print("  ⏳ HF 모델 웜업 중, 15초 대기...")
                time.sleep(15)
                continue
            print(f"  ⚠ HF 응답 {r.status_code} → 무료 대체 서버로 전환합니다.")
            return False
        except Exception as e:
            print(f"  ⚠ HF 오류: {e}")
            return False
    return False


def gen_image_pollinations(prompt, out_path):
    """키 불필요, 무제한 무료 (pollinations.ai)"""
    url = ("https://image.pollinations.ai/prompt/"
           + urllib.parse.quote(prompt)
           + "?width=1080&height=1080&nologo=true&model=flux")
    try:
        r = requests.get(url, timeout=180)
        if r.status_code == 200 and len(r.content) > 10000:
            with open(out_path, "wb") as f:
                f.write(r.content)
            return True
        print(f"  ⚠ Pollinations 응답 이상: {r.status_code}")
        return False
    except Exception as e:
        print(f"  ⚠ Pollinations 오류: {e}")
        return False


def generate_image(topic, channel, cfg):
    print("\n🎨 [Step 3] 카드뉴스 배경 이미지 생성 중... (10~60초)")
    prompt = build_image_prompt(topic, channel)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(IMG_DIR, f"card_bg_{ts}.png")

    token = cfg.get("hf_token", "").strip()
    ok = False
    if token:
        print("  → 허깅페이스 FLUX 시도...")
        ok = gen_image_hf(prompt, token, out_path)
    if not ok:
        print("  → Pollinations 무료 서버 사용...")
        ok = gen_image_pollinations(prompt, out_path)

    if ok:
        print(f"  💾 저장 완료: {out_path}")
        return out_path
    print("  ❌ 이미지 생성 실패 (인터넷 연결 확인 후 재시도)")
    return None


# ==========================================================
# 4. 클로드 프롬프트 조립 (트리플 검증 + 플랫폼별 원고)
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

    prompt = f"""당신은 SNS 마케팅 콘텐츠 전문가입니다. 아래 뉴스와 채널 정보를 바탕으로 플랫폼별 콘텐츠 세트를 제작해주세요.

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
    return prompt


def deliver_prompt(prompt_text):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join(PROMPT_DIR, f"claude_prompt_{ts}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(prompt_text)

    copied = False
    if HAS_CLIPBOARD:
        try:
            pyperclip.copy(prompt_text)
            copied = True
        except Exception:
            pass

    print("\n📝 [Step 4] 클로드 프롬프트 준비 완료!")
    if copied:
        print("  ✅ 클립보드에 자동 복사되었습니다 → 클로드 앱에 Ctrl+V 하세요!")
    else:
        print("  💾 아래 파일을 열어 내용을 복사한 뒤 클로드 앱에 붙여넣으세요:")
    print(f"  📄 백업 파일: {txt_path}")
    return txt_path


# ==========================================================
# 5. 자가 판올림 (가이드라인 버전업)
# ==========================================================
def check_algorithm_update(user_input, guidelines):
    if user_input.startswith("[알고리즘 업데이트]:"):
        note = user_input.replace("[알고리즘 업데이트]:", "").strip()
        if note:
            guidelines["trend_notes"].append(
                f"{datetime.now().strftime('%Y-%m-%d')} | {note}")
            # 버전 판올림 (1.0 → 1.1 → ...)
            try:
                major, minor = guidelines.get("version", "1.0").split(".")
                guidelines["version"] = f"{major}.{int(minor)+1}"
            except Exception:
                guidelines["version"] = "1.1"
            guidelines["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_json(GUIDE_PATH, guidelines)
            print(f"  🔄 가이드라인 v{guidelines['version']} 판올림 완료! 다음 프롬프트부터 반영됩니다.")
            return True
    return False


# ==========================================================
# 메인 실행 흐름
# ==========================================================
def main():
    print("=" * 55)
    print("🚀 SNS 트렌드 콘텐츠 반자동화 시스템 v1.0 (무료)")
    print("=" * 55)

    cfg, channels_data, guidelines, history, rss = load_all_configs()

    if "입력" in cfg.get("naver_client_id", ""):
        print("\n⚠ 네이버 API 키가 아직 설정되지 않았습니다.")
        print("  → config.json 을 열어 Client ID/Secret 을 입력하면 국내 뉴스도 수집됩니다.")
        print("  → 지금은 해외 RSS만으로 진행합니다.\n")

    # 채널 선택 (추가/삭제 포함)
    channel = manage_channels(channels_data)
    print(f"\n✅ 선택된 채널: {channel['name']}")
    print(f"   톤앤매너: {channel['tone']}")

    # 뉴스 수집 + 적합도 정렬
    news_list = collect_news(cfg, channel, rss, history)
    if not news_list:
        print("❌ 수집된 뉴스가 없습니다. 인터넷 연결 또는 API 키를 확인하세요.")
        return

    print("\n" + "=" * 55)
    print(f"🔥 '{channel['name']}' 적합도순 핫이슈 TOP {len(news_list)}")
    print("=" * 55)
    for i, n in enumerate(news_list, 1):
        flag = "🌏해외" if n["lang"] == "en" else "🇰🇷국내"
        star = "⭐" * min(n["score"], 5)
        print(f"  {i:2d}. [{flag}] {n['title'][:52]}")
        print(f"       └ {n['source']} {star}")

    print("-" * 55)
    print("  뉴스 번호 입력 | 또는 [알고리즘 업데이트]: 내용 입력")
    while True:
        sel = input("> ").strip()
        if check_algorithm_update(sel, guidelines):
            continue
        if sel.isdigit() and 1 <= int(sel) <= len(news_list):
            news = news_list[int(sel) - 1]
            break
        print("  ⚠ 올바른 번호를 입력하세요.")

    print(f"\n✅ 채택된 뉴스: {news['title']}")
    if news["lang"] == "en":
        print("  🌏 해외 기사 → 프롬프트에 '트리플 검증(번역→윤문→교차검증)' 절차가 포함됩니다.")

    # 이미지 생성 (무료)
    img_path = generate_image(news["title"], channel, cfg)

    # 프롬프트 조립 + 클립보드
    prompt = build_claude_prompt(news, channel, guidelines, img_path)
    deliver_prompt(prompt)

    # 히스토리 기록 (중복 방지)
    history["used"].append({
        "title": news["title"], "link": news.get("link", ""),
        "channel": channel["name"],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_json(HISTORY_PATH, history)

    print("\n" + "=" * 55)
    print("🎉 완료! 작업 순서:")
    print("  1) 클로드 앱을 열고 Ctrl+V → 3종 콘텐츠 세트 받기")
    print(f"  2) 배경 이미지: {img_path if img_path else '(실패)'}")
    print("  3) 미리캔버스/캔바에서 이미지+자막 조합 → 발행")
    print("=" * 55)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n종료합니다.")
