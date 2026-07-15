#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
자막 도구 v8
- 영상 미리보기: 슬라이더로 장면을 넘겨보며 자막 타이밍 지정
- [▶ 여기부터] [⏹ 여기까지] 버튼으로 현재 화면 시간을 바로 입력
- 자막 스타일: 글꼴 / 색상 / 크기 / 위치(상단·중앙·하단) 설정
- 미리보기 화면에 자막이 실제 모습으로 표시됨
- ffmpeg / Pillow 자동 설치
"""

import sys
import os
import io
import re
import subprocess
import threading
from pathlib import Path
from datetime import datetime

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def pip_install(pkg):
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", pkg],
                       capture_output=True, text=True, timeout=600, creationflags=NOWIN)
    return r.returncode == 0, r.stderr


def ensure_deps():
    """ffmpeg + Pillow 자동 설치"""
    errs = []
    try:
        import imageio_ffmpeg  # noqa
    except ImportError:
        ok, e = pip_install("imageio-ffmpeg")
        if not ok:
            errs.append("imageio-ffmpeg: " + e[:200])
    try:
        from PIL import Image  # noqa
    except ImportError:
        ok, e = pip_install("Pillow")
        if not ok:
            errs.append("Pillow: " + e[:200])
    try:
        import imageio_ffmpeg
        from PIL import Image  # noqa
        return True, imageio_ffmpeg.get_ffmpeg_exe(), errs
    except ImportError:
        return False, None, errs


def get_duration(ffmpeg, video):
    """ffmpeg -i 출력에서 영상 길이(초) 파싱 (인코딩 안전)"""
    r = subprocess.run([ffmpeg, "-i", str(video)], capture_output=True,
                       creationflags=NOWIN)  # 바이트로 받음
    err = (r.stderr or b"").decode("utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if not m:
        err2 = (r.stderr or b"").decode("cp949", errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err2)
    if not m:
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def grab_frame(ffmpeg, video, t):
    """t초 지점의 프레임을 PNG 바이트로 추출"""
    r = subprocess.run(
        [ffmpeg, "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, creationflags=NOWIN)
    return r.stdout if r.returncode == 0 and r.stdout else None


def esc_drawtext(t):
    for a, b in [("\\", "\\\\"), ("'", "\\'"), (":", "\\:"), (",", "\\,"),
                 ("%", "\\%"), ("[", "\\["), ("]", "\\]"), (";", "\\;")]:
        t = t.replace(a, b)
    return t


def find_fonts():
    """상업적 사용 무료 한글 폰트만 표시 (화이트리스트)
    - 나눔/노토/프리텐다드/지마켓산스/검은고딕/주아/도현 등
    - 눈누(noonnu.cc)에서 무료폰트 설치하면 자동으로 목록에 추가됨"""
    FREE_PATTERNS = [
        ("나눔고딕", "nanumgothic"),
        ("나눔스퀘어", "nanumsquare"),
        ("나눔바른고딕", "nanumbarun"),
        ("노토산스 KR", "notosanskr"),
        ("노토산스 CJK", "notosanscjk"),
        ("프리텐다드", "pretendard"),
        ("지마켓산스", "gmarket"),
        ("검은고딕", "blackhan"),
        ("배민 주아", "jua"),
        ("배민 도현", "dohyeon"),
        ("스포카한산스", "spoqa"),
        ("에스코어드림", "score"),
        ("카페24", "cafe24"),
        ("여기어때 잘난체", "jalnan"),
        ("D2Coding", "d2coding"),
    ]
    dirs = [Path(r"C:\Windows\Fonts"),
            Path.home() / "AppData/Local/Microsoft/Windows/Fonts"]
    fonts = []
    seen = set()
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            fname = f.stem.lower().replace(" ", "").replace("-", "").replace("_", "")
            for label, pat in FREE_PATTERNS:
                if pat in fname and str(f).lower() not in seen:
                    seen.add(str(f).lower())
                    # Bold/두께 표기 유지
                    suffix = ""
                    low = f.stem.lower()
                    if "bold" in low or "bd" in low: suffix = " 굵게"
                    elif "extrabold" in low or "black" in low: suffix = " 아주굵게"
                    elif "light" in low: suffix = " 얇게"
                    fonts.append((label + suffix, str(f)))
                    break
    if not fonts:
        # 무료폰트가 하나도 없으면 기본 폰트로라도 동작 (자막이 안 나오는 것 방지)
        mal = r"C:\Windows\Fonts\malgunbd.ttf"
        if os.path.exists(mal):
            fonts = [("(무료폰트 없음-맑은고딕 사용)", mal)]
        else:
            fonts = [("기본", "")]
    return fonts


COLORS = [("흰색", "#FFFFFF"), ("노랑", "#FFE400"), ("빨강", "#FF3B30"),
          ("초록", "#34C759"), ("파랑", "#0A84FF"), ("검정", "#000000")]


import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk, colorchooser


class App:
    def __init__(self, root):
        self.root = root
        root.title("✂️ 자막 도구 v8 — 영상 보면서 자막 넣기")
        root.geometry("1080x760")
        root.minsize(980, 700)

        self.ffmpeg = None
        self.video = None
        self.duration = 0.0
        self.cur_t = 0.0
        self.subs = []            # {"start","end","text"}
        self.frame_img = None     # PIL 원본 프레임
        self.tk_img = None
        self.fonts = find_fonts()
        self._seek_job = None
        self._grabbing = False   # 프레임 추출 중복 방지
        self.playing = False

        self._build_ui()
        self.log("🔧 ffmpeg / Pillow 확인·설치 중... (첫 실행 1~2분)")
        threading.Thread(target=self._setup, daemon=True).start()

    # ================= UI =================
    def _build_ui(self):
        top = tk.Frame(self.root, bg="#6C5CE7")
        top.pack(fill=tk.X)
        tk.Label(top, text="✂️ 자막 도구 v8 — 영상 보면서 자막 넣기",
                 font=("맑은 고딕", 13, "bold"), bg="#6C5CE7", fg="white").pack(pady=8)

        body = tk.Frame(self.root, bg="white")
        body.pack(fill=tk.BOTH, expand=True)

        # ---- 왼쪽: 미리보기 ----
        left = tk.Frame(body, bg="white")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=8)

        lrow = tk.Frame(left, bg="white")
        lrow.pack(fill=tk.X)
        tk.Button(lrow, text="📂 영상 열기", bg="#6C5CE7", fg="white",
                  font=("맑은 고딕", 10, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self.pick_video).pack(side=tk.LEFT)
        self.vlabel = tk.Label(lrow, text="영상을 선택하세요", bg="white", fg="#888",
                               font=("맑은 고딕", 9))
        self.vlabel.pack(side=tk.LEFT, padx=8)

        # 미리보기 (고정 크기 - 창 커짐 방지)
        holder = tk.Frame(left, bg="#222", width=600, height=420)
        holder.pack(pady=6)
        holder.pack_propagate(False)
        self.canvas = tk.Label(holder, bg="#222", text="미리보기", fg="#777",
                               font=("맑은 고딕", 12))
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 시간 슬라이더
        srow = tk.Frame(left, bg="white")
        srow.pack(fill=tk.X)
        self.time_label = tk.Label(srow, text="0.0초 / 0.0초", bg="white",
                                   font=("맑은 고딕", 9, "bold"))
        self.time_label.pack(side=tk.RIGHT)
        self.slider = ttk.Scale(left, from_=0, to=100, orient=tk.HORIZONTAL,
                                command=self.on_slide)
        self.slider.pack(fill=tk.X, pady=(0, 4))

        # 미세 이동 버튼
        step = tk.Frame(left, bg="white")
        step.pack()
        self.play_btn = tk.Button(step, text="▶ 재생", font=("맑은 고딕", 9, "bold"),
                                  bg="#34C759", fg="white", relief=tk.FLAT, width=8,
                                  cursor="hand2", command=self.toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=4)
        for txt, dt in [("◀◀ -5초", -5), ("◀ -1초", -1), ("-0.2", -0.2),
                        ("+0.2", 0.2), ("+1초 ▶", 1), ("+5초 ▶▶", 5)]:
            tk.Button(step, text=txt, font=("맑은 고딕", 8), relief=tk.FLAT,
                      bg="#EEE", cursor="hand2",
                      command=lambda d=dt: self.step(d)).pack(side=tk.LEFT, padx=2)

        # ---- 오른쪽: 자막/스타일 ----
        right = tk.Frame(body, bg="#F7F7FB", width=430)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        # 자막 입력
        f_in = tk.LabelFrame(right, text=" ✍️ 자막 추가 ", bg="#F7F7FB",
                             font=("맑은 고딕", 9, "bold"))
        f_in.pack(fill=tk.X, padx=8, pady=6)

        trow = tk.Frame(f_in, bg="#F7F7FB")
        trow.pack(fill=tk.X, padx=6, pady=3)
        tk.Button(trow, text="▶ 여기부터", bg="#34C759", fg="white",
                  font=("맑은 고딕", 9, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self.set_start).pack(side=tk.LEFT)
        self.start_var = tk.StringVar(value="0")
        tk.Entry(trow, textvariable=self.start_var, width=7,
                 font=("맑은 고딕", 9)).pack(side=tk.LEFT, padx=4)
        tk.Button(trow, text="⏹ 여기까지", bg="#FF3B30", fg="white",
                  font=("맑은 고딕", 9, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self.set_end).pack(side=tk.LEFT, padx=(8, 0))
        self.end_var = tk.StringVar(value="3")
        tk.Entry(trow, textvariable=self.end_var, width=7,
                 font=("맑은 고딕", 9)).pack(side=tk.LEFT, padx=4)

        tk.Label(f_in, text="💡 두 줄 자막: 줄 바꿀 곳에 / 입력  (예: 이 가격 실화?/지금 바로 확인)",
                 bg="#F7F7FB", fg="#888", font=("맑은 고딕", 8)).pack(anchor=tk.W, padx=6)
        self.text_var = tk.StringVar()
        self.text_entry = tk.Entry(f_in, font=("맑은 고딕", 11), textvariable=self.text_var)
        self.text_entry.pack(fill=tk.X, padx=6, pady=3, ipady=3)
        self.text_var.trace_add("write", lambda *a: self.refresh_preview_overlay())
        # 한글 IME 조합 중에도 갱신되도록 0.3초마다 내용 확인 (폴링)
        self._last_text = ""
        self._poll_text()

        tk.Button(f_in, text="➕ 자막 목록에 추가", bg="#FFD93D",
                  font=("맑은 고딕", 10, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self.add_sub).pack(fill=tk.X, padx=6, pady=4)

        # 자막 목록
        f_list = tk.LabelFrame(right, text=" 📜 자막 목록 (클릭하면 그 장면으로 이동) ",
                               bg="#F7F7FB", font=("맑은 고딕", 9, "bold"))
        f_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.listbox = tk.Listbox(f_list, font=("맑은 고딕", 9), height=7)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=3)
        self.listbox.bind("<<ListboxSelect>>", self.on_pick_sub)
        tk.Button(f_list, text="🗑 선택한 자막 삭제", bg="#DDD",
                  font=("맑은 고딕", 9), relief=tk.FLAT, cursor="hand2",
                  command=self.del_sub).pack(fill=tk.X, padx=6, pady=3)

        # 스타일
        f_st = tk.LabelFrame(right, text=" 🎨 자막 스타일 ", bg="#F7F7FB",
                             font=("맑은 고딕", 9, "bold"))
        f_st.pack(fill=tk.X, padx=8, pady=4)

        r1 = tk.Frame(f_st, bg="#F7F7FB"); r1.pack(fill=tk.X, padx=6, pady=2)
        tk.Label(r1, text="글꼴:", bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        self.font_var = tk.StringVar(value=self.fonts[0][0])
        ttk.Combobox(r1, textvariable=self.font_var, state="readonly", width=14,
                     values=[n for n, _ in self.fonts]).pack(side=tk.LEFT, padx=4)
        tk.Label(r1, text="크기:", bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT, padx=(8, 0))
        self.size_var = tk.IntVar(value=48)
        tk.Spinbox(r1, from_=20, to=120, increment=4, textvariable=self.size_var,
                   width=5, command=self.refresh_preview_overlay).pack(side=tk.LEFT, padx=4)

        r2 = tk.Frame(f_st, bg="#F7F7FB"); r2.pack(fill=tk.X, padx=6, pady=2)
        tk.Label(r2, text="색상:", bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        self.color_var = tk.StringVar(value="#FFFFFF")
        for name, hexv in COLORS:
            tk.Button(r2, bg=hexv, width=2, relief=tk.SOLID, bd=1, cursor="hand2",
                      command=lambda h=hexv: self.set_color(h)).pack(side=tk.LEFT, padx=1)
        tk.Button(r2, text="직접선택", font=("맑은 고딕", 8), relief=tk.FLAT,
                  bg="#EEE", cursor="hand2", command=self.pick_color).pack(side=tk.LEFT, padx=4)
        self.color_chip = tk.Label(r2, bg="#FFFFFF", width=3, relief=tk.SOLID, bd=1)
        self.color_chip.pack(side=tk.LEFT, padx=2)

        r3 = tk.Frame(f_st, bg="#F7F7FB"); r3.pack(fill=tk.X, padx=6, pady=2)
        tk.Label(r3, text="위치:", bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        self.pos_var = tk.StringVar(value="하단")
        for p in ["상단", "중앙", "하단"]:
            tk.Radiobutton(r3, text=p, variable=self.pos_var, value=p, bg="#F7F7FB",
                           font=("맑은 고딕", 9),
                           command=self.refresh_preview_overlay).pack(side=tk.LEFT)

        r3b = tk.Frame(f_st, bg="#F7F7FB"); r3b.pack(fill=tk.X, padx=6, pady=2)
        tk.Label(r3b, text="미세조절:", bg="#F7F7FB",
                 font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        self.offset_var = tk.IntVar(value=0)
        tk.Scale(r3b, from_=-300, to=300, orient=tk.HORIZONTAL, length=200,
                 variable=self.offset_var, bg="#F7F7FB", highlightthickness=0,
                 command=lambda v: self.refresh_preview_overlay()
                 ).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        tk.Label(r3b, text="◀위 아래▶", bg="#F7F7FB", fg="#888",
                 font=("맑은 고딕", 8)).pack(side=tk.LEFT)

        self.font_var.trace_add("write", lambda *a: self.refresh_preview_overlay())

        # 기존 자막 처리
        f_rm = tk.LabelFrame(right, text=" ⬛ 기존 자막 처리 ", bg="#F7F7FB",
                             font=("맑은 고딕", 9, "bold"))
        f_rm.pack(fill=tk.X, padx=8, pady=4)
        r4 = tk.Frame(f_rm, bg="#F7F7FB"); r4.pack(fill=tk.X, padx=6, pady=2)
        self.mode = tk.StringVar(value="box")
        tk.Radiobutton(r4, text="박스덮기", variable=self.mode, value="box",
                       bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        tk.Radiobutton(r4, text="크롭", variable=self.mode, value="crop",
                       bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        tk.Radiobutton(r4, text="안 함", variable=self.mode, value="overlay",
                       bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        tk.Label(r4, text="영역", bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT, padx=(8, 0))
        self.area_var = tk.StringVar(value="15")
        tk.Entry(r4, textvariable=self.area_var, width=4,
                 font=("맑은 고딕", 9)).pack(side=tk.LEFT, padx=2)
        tk.Label(r4, text="%", bg="#F7F7FB", font=("맑은 고딕", 9)).pack(side=tk.LEFT)

        # 변환 + 로그
        self.go_btn = tk.Button(right, text="🚀 변환 시작", font=("맑은 고딕", 12, "bold"),
                                bg="#6C5CE7", fg="white", height=2, relief=tk.FLAT,
                                cursor="hand2", command=self.start_render)
        self.go_btn.pack(fill=tk.X, padx=8, pady=6)

        self.log_box = scrolledtext.ScrolledText(right, height=6,
                                                 font=("Consolas", 8), bg="#EFEFF4")
        self.log_box.pack(fill=tk.X, padx=8, pady=(0, 8))

    # ================= 동작 =================
    def _poll_text(self):
        """한글 입력 중에도 미리보기 실시간 갱신"""
        try:
            cur = self.text_entry.get()
            if cur != self._last_text:
                self._last_text = cur
                self.refresh_preview_overlay()
        except Exception:
            pass
        self.root.after(300, self._poll_text)

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_box.see(tk.END)

    def _setup(self):
        ok, ff, errs = ensure_deps()
        for e in errs:
            self.log("⚠️ " + e)
        if ok:
            self.ffmpeg = ff
            self.log("✅ 준비 완료! 영상을 열어주세요.")
        else:
            self.log("❌ 자동 설치 실패. 관리자 cmd에서:")
            self.log(f'  "{sys.executable}" -m pip install imageio-ffmpeg Pillow')

    def pick_video(self):
        if not self.ffmpeg:
            self.log("⏳ 아직 준비 중입니다. 잠시 후 다시 시도해주세요.")
            return
        p = filedialog.askopenfilename(
            title="영상 선택",
            filetypes=[("영상", "*.mp4 *.mov *.mkv *.webm *.avi"), ("모든 파일", "*.*")])
        if not p:
            return
        self.video = Path(p)
        self.vlabel.config(text=self.video.name, fg="#333")
        d = get_duration(self.ffmpeg, self.video)
        if not d:
            from tkinter import simpledialog
            d = simpledialog.askfloat("영상 길이", 
                "영상 길이를 자동으로 읽지 못했습니다.\n영상 길이를 초 단위로 입력해주세요\n(예: 45 또는 90.5):",
                parent=self.root, minvalue=1)
            if not d:
                return
        self.duration = d
        self.slider.config(to=d)
        self.log(f"🎞 {self.video.name} ({d:.1f}초)")
        self.seek(0)

    # --- 탐색/미리보기 ---
    def on_slide(self, val):
        if not self.video:
            return
        t = float(val)
        self.cur_t = t
        self.time_label.config(text=f"{t:.1f}초 / {self.duration:.1f}초")
        # 슬라이더를 드래그하는 동안 과도한 추출 방지 (0.15초 디바운스)
        if self._seek_job:
            self.root.after_cancel(self._seek_job)
        self._seek_job = self.root.after(150, lambda: self.seek(t))

    def step(self, dt):
        if not self.video:
            return
        t = min(max(0, self.cur_t + dt), self.duration)
        self.slider.set(t)

    def seek(self, t):
        if not self.video or self._grabbing:
            return
        self._grabbing = True
        def work():
            try:
                data = grab_frame(self.ffmpeg, self.video, t)
                if data:
                    self.root.after(0, lambda: self._show_frame(data))
            finally:
                self._grabbing = False
        threading.Thread(target=work, daemon=True).start()

    # ---- 재생 ----
    def toggle_play(self):
        if not self.video:
            return
        if self.playing:
            self.playing = False
            self.play_btn.config(text="▶ 재생", bg="#34C759")
        else:
            self.playing = True
            self.play_btn.config(text="⏸ 정지", bg="#FF9500")
            import time
            self._play_wall = time.time()
            self._play_from = self.cur_t
            self._play_tick()

    def _play_tick(self):
        if not self.playing:
            return
        import time
        t = self._play_from + (time.time() - self._play_wall)
        if t >= self.duration:
            self.playing = False
            self.play_btn.config(text="▶ 재생", bg="#34C759")
            return
        self.cur_t = t
        self.time_label.config(text=f"{t:.1f}초 / {self.duration:.1f}초")
        # 슬라이더 이동 (on_slide 재호출 방지 위해 직접 seek)
        self.slider.set(t)
        self.root.after(250, self._play_tick)

    def _show_frame(self, png_bytes):
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        self.frame_img = img
        self.refresh_preview_overlay()

    def refresh_preview_overlay(self):
        """현재 프레임 + 자막/박스 미리보기 렌더"""
        if self.frame_img is None:
            return
        from PIL import Image, ImageDraw, ImageFont, ImageTk

        img = self.frame_img.copy()
        w, h = img.size
        draw = ImageDraw.Draw(img)

        # 기존 자막 처리 미리보기
        try:
            area = float(self.area_var.get()) / 100.0
        except ValueError:
            area = 0.15
        if self.mode.get() == "box":
            draw.rectangle([0, int(h * (1 - area)), w, h], fill="black")
        elif self.mode.get() == "crop":
            img = img.crop((0, 0, w, int(h * (1 - area))))
            w, h = img.size
            draw = ImageDraw.Draw(img)

        # 자막 미리보기 (입력창의 텍스트)
        text = (self.text_entry.get().strip() or "자막 미리보기").replace("/", "\n")
        fpath = dict(self.fonts).get(self.font_var.get(), "")
        size = int(self.size_var.get())
        try:
            font = ImageFont.truetype(fpath, size) if fpath else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=6)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (w - tw) // 2
        pos = self.pos_var.get()
        off = int(self.offset_var.get())
        if pos == "상단":
            y = 30 + off
        elif pos == "중앙":
            y = (h - th) // 2 + off
        else:
            y = h - th - 40 + off
        y = max(0, min(y, h - th))  # 화면 밖으로 못 나가게

        # 테두리(스트로크) + 본문
        try:
            draw.multiline_text((x, y), text, font=font, fill=self.color_var.get(),
                      stroke_width=3, stroke_fill="black", spacing=6, align="center")
        except TypeError:
            draw.multiline_text((x, y), text, font=font, fill=self.color_var.get(),
                      spacing=6, align="center")

        # 화면 크기에 맞게 축소
        img.thumbnail((596, 416))  # 고정 크기 (창 커짐 방지)
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.config(image=self.tk_img, text="")

    # --- 자막 목록 ---
    def set_start(self):
        self.start_var.set(f"{self.cur_t:.1f}")

    def set_end(self):
        self.end_var.set(f"{self.cur_t:.1f}")

    def add_sub(self):
        text = self.text_entry.get().strip()
        if not text:
            messagebox.showerror("오류", "자막 문구를 입력해주세요")
            return
        try:
            s, e = float(self.start_var.get()), float(self.end_var.get())
        except ValueError:
            messagebox.showerror("오류", "시간은 숫자로 입력해주세요")
            return
        if e <= s:
            messagebox.showerror("오류", "끝 시간이 시작보다 커야 합니다")
            return
        self.subs.append({"start": s, "end": e, "text": text})
        self.subs.sort(key=lambda x: x["start"])
        self._refresh_list()
        self.text_entry.delete(0, tk.END)
        self.log(f"➕ [{s:.1f}~{e:.1f}] {text}")

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for sub in self.subs:
            self.listbox.insert(tk.END,
                                f"[{sub['start']:.1f} ~ {sub['end']:.1f}]  {sub['text']}")

    def on_pick_sub(self, _):
        sel = self.listbox.curselection()
        if not sel:
            return
        sub = self.subs[sel[0]]
        # 문구/시간을 입력칸에 채우기 (미리보기에도 자동 반영됨)
        self.text_var.set(sub["text"])
        self.start_var.set(f"{sub['start']:.1f}")
        self.end_var.set(f"{sub['end']:.1f}")
        if self.video:
            self.slider.set(sub["start"])
        self.refresh_preview_overlay()

    def del_sub(self):
        sel = self.listbox.curselection()
        if sel:
            removed = self.subs.pop(sel[0])
            self._refresh_list()
            self.log(f"🗑 삭제: {removed['text']}")

    # --- 렌더 ---
    def start_render(self):
        if not self.video:
            messagebox.showerror("오류", "영상을 먼저 선택해주세요")
            return
        if not self.subs:
            if not messagebox.askyesno("확인", "자막이 없습니다. 그래도 진행할까요?"):
                return
        out = filedialog.asksaveasfilename(
            title="완성 영상 저장 위치와 이름을 정하세요",
            initialdir=str(self.video.parent),
            initialfile=self.video.stem + "_자막완성.mp4",
            defaultextension=".mp4",
            filetypes=[("MP4 영상", "*.mp4")])
        if not out:
            return
        self._out_path = Path(out)
        self.go_btn.config(state=tk.DISABLED, text="⏳ 변환 중...")
        threading.Thread(target=self._render, daemon=True).start()

    def _render(self):
        try:
            try:
                area = float(self.area_var.get()) / 100.0
            except ValueError:
                area = 0.15
            fpath = dict(self.fonts).get(self.font_var.get(), "")
            size = int(self.size_var.get())
            color = self.color_var.get().replace("#", "0x")
            pos = self.pos_var.get()
            mode = self.mode.get()
            out = self._out_path

            filters = []
            if mode == "crop":
                filters.append(f"crop=iw:ih*{1-area:.3f}:0:0")
            elif mode == "box":
                filters.append(f"drawbox=x=0:y=ih*{1-area:.3f}:w=iw:h=ih*{area:.3f}"
                               f":color=black:t=fill")

            off = int(self.offset_var.get())
            if pos == "상단":
                ypos = f"({30 + off})"
            elif pos == "중앙":
                ypos = f"((h-text_h)/2+({off}))"
            else:
                ypos = f"(h-text_h-40+({off}))"

            ffp = fpath.replace("\\", "/").replace(":", "\\:")
            import tempfile
            self._tmpdir = tempfile.mkdtemp(prefix="subs_")
            for i, sub in enumerate(self.subs):
                # 자막을 파일로 저장 (줄바꿈/특수문자 완전 안전)
                tf = os.path.join(self._tmpdir, f"s{i}.txt")
                with open(tf, "w", encoding="utf-8") as fh:
                    fh.write(sub["text"].replace("/", "\n"))
                tfp = tf.replace("\\", "/").replace(":", "\\:")
                filters.append(
                    f"drawtext=fontfile='{ffp}':textfile='{tfp}':fontsize={size}"
                    f":fontcolor={color}:borderw=3:bordercolor=black:line_spacing=8"
                    f":x=(w-text_w)/2:y={ypos}"
                    f":enable='between(t,{sub['start']:.2f},{sub['end']:.2f})'")

            vf = ",".join(filters) if filters else "null"
            cmd = [self.ffmpeg, "-y", "-i", str(self.video), "-vf", vf,
                   "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                   "-c:a", "copy", str(out)]

            self.log("=" * 40)
            self.log(f"🎬 변환 시작 ({len(self.subs)}개 자막)")
            r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NOWIN)

            if r.returncode == 0 and out.exists():
                self.log(f"✅ 완료! → {out.name}")
                self.root.after(0, lambda: messagebox.showinfo("성공", f"완료!\n{out}"))
            else:
                self.log("❌ 실패:\n" + (r.stderr or "")[-400:])
        except Exception as e:
            self.log(f"❌ 오류: {e}")
        finally:
            self.root.after(0, lambda: self.go_btn.config(
                state=tk.NORMAL, text="🚀 변환 시작"))

    def set_color(self, hexv):
        self.color_var.set(hexv)
        self.color_chip.config(bg=hexv)
        self.refresh_preview_overlay()

    def pick_color(self):
        c = colorchooser.askcolor(title="자막 색상")[1]
        if c:
            self.set_color(c)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
