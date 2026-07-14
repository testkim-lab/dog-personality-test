#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
영상 다운로더 v3
- 왼쪽 사이드바: 사이트 바로가기 (직접 추가/삭제 가능, 최대 15개)
- 설정은 이 파일과 같은 폴더의 sites_config.json에 저장됨
  → 폴더째 복사하면 다른 컴퓨터에서도 그대로 사용 가능
- yt-dlp 자동 설치, ffmpeg 불필요
"""

import sys
import os
import subprocess
import threading
import re
import json
import webbrowser
from pathlib import Path
from datetime import datetime

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "sites_config.json"
MAX_SITES = 15

DEFAULT_SITES = [
    {"name": "쿠팡파트너스", "url": "https://partners.coupang.com/"},
    {"name": "네이버", "url": "https://www.naver.com/"},
    {"name": "유튜브", "url": "https://www.youtube.com/"},
    {"name": "인스타", "url": "https://www.instagram.com/"},
    {"name": "틱톡", "url": "https://www.tiktok.com/"},
    {"name": "스레드", "url": "https://www.threads.net/"},
]


# ============================================
# yt-dlp 자동 설치
# ============================================
def ensure_ytdlp():
    try:
        import yt_dlp  # noqa
        return True, ""
    except ImportError:
        pass
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            return False, result.stderr
        import yt_dlp  # noqa
        return True, ""
    except Exception as e:
        return False, str(e)


import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog


class App:
    def __init__(self, root):
        self.root = root
        root.title("🎬 영상 다운로더 v3")
        root.geometry("920x680")
        root.minsize(820, 600)

        self.download_path = APP_DIR
        self.ytdlp_ready = False
        self.sites = self._load_sites()

        self._build_ui()

        self.log("🔧 yt-dlp 확인/설치 중... 잠시만 기다려주세요")
        threading.Thread(target=self._setup_ytdlp, daemon=True).start()

    # ---------- 설정 저장/불러오기 ----------
    def _load_sites(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sites = data.get("sites", [])
                if sites:
                    return sites[:MAX_SITES]
            except Exception:
                pass
        return list(DEFAULT_SITES)

    def _save_sites(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"sites": self.sites}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"⚠️ 설정 저장 실패: {e}")

    # ---------- UI ----------
    def _build_ui(self):
        # 헤더
        top = tk.Frame(self.root, bg="#FF6B6B")
        top.pack(fill=tk.X)
        tk.Label(top, text="🎬 영상 다운로더 v3  (검은창 없는 버전)", font=("맑은 고딕", 14, "bold"),
                 bg="#FF6B6B", fg="white").pack(pady=10)

        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        # ===== 왼쪽 사이드바 =====
        sidebar = tk.Frame(body, bg="#F0F2F5", width=220)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="📱 내 사이트", font=("맑은 고딕", 11, "bold"),
                 bg="#F0F2F5", fg="#333").pack(anchor=tk.W, padx=12, pady=(14, 6))

        # 사이트 버튼 영역 (스크롤 가능)
        self.site_frame = tk.Frame(sidebar, bg="#F0F2F5")
        self.site_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        self._render_site_buttons()

        # 사이트 추가/삭제 버튼
        manage = tk.Frame(sidebar, bg="#F0F2F5")
        manage.pack(fill=tk.X, padx=10, pady=6)
        tk.Button(manage, text="➕ 사이트 추가", bg="#FFD93D", fg="#333",
                  font=("맑은 고딕", 9, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self.add_site).pack(fill=tk.X, pady=2)
        tk.Button(manage, text="➖ 사이트 삭제", bg="#DDDDDD", fg="#333",
                  font=("맑은 고딕", 9), relief=tk.FLAT, cursor="hand2",
                  command=self.delete_site).pack(fill=tk.X, pady=2)

        # 저장 경로
        tk.Label(sidebar, text="💾 저장 폴더", font=("맑은 고딕", 10, "bold"),
                 bg="#F0F2F5", fg="#333").pack(anchor=tk.W, padx=12, pady=(10, 2))
        self.path_label = tk.Label(sidebar, text=self._short_path(self.download_path),
                                   font=("맑은 고딕", 8), bg="#E4E6EB", fg="#555",
                                   wraplength=190, justify=tk.LEFT, anchor=tk.W)
        self.path_label.pack(fill=tk.X, padx=10, pady=2, ipady=4)
        tk.Button(sidebar, text="📁 경로 변경", bg="#4ECDC4", fg="white",
                  font=("맑은 고딕", 9, "bold"), relief=tk.FLAT, cursor="hand2",
                  command=self.change_path).pack(fill=tk.X, padx=10, pady=(2, 14))

        # ===== 오른쪽 메인 =====
        main = tk.Frame(body, bg="white")
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        tk.Label(main, text="영상 URL:", font=("맑은 고딕", 10, "bold"),
                 bg="white").pack(anchor=tk.W)
        self.url_entry = tk.Entry(main, font=("맑은 고딕", 11))
        self.url_entry.pack(fill=tk.X, pady=(2, 8), ipady=4)

        row = tk.Frame(main, bg="white")
        row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row, text="파일명(선택):", font=("맑은 고딕", 9), bg="white").pack(side=tk.LEFT)
        self.name_entry = tk.Entry(row, font=("맑은 고딕", 10))
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        self.dl_btn = tk.Button(main, text="🚀 영상 다운로드 시작",
                                font=("맑은 고딕", 12, "bold"),
                                bg="#FF6B6B", fg="white", height=2,
                                relief=tk.FLAT, cursor="hand2",
                                command=self.start_download)
        self.dl_btn.pack(fill=tk.X, pady=(4, 10))

        tk.Label(main, text="📋 진행 상황:", font=("맑은 고딕", 9, "bold"),
                 bg="white").pack(anchor=tk.W)
        self.log_box = scrolledtext.ScrolledText(main, height=16,
                                                 font=("Consolas", 9), bg="#F5F5F5")
        self.log_box.pack(fill=tk.BOTH, expand=True)

        bottom = tk.Frame(main, bg="white")
        bottom.pack(fill=tk.X, pady=(8, 0))
        tk.Button(bottom, text="📂 저장 폴더 열기", bg="#4ECDC4", fg="white",
                  relief=tk.FLAT, cursor="hand2",
                  command=self.open_folder).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(bottom, text="🧹 로그 지우기", bg="#DDD",
                  relief=tk.FLAT, cursor="hand2",
                  command=lambda: self.log_box.delete("1.0", tk.END)
                  ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

    def _render_site_buttons(self):
        """사이드바 사이트 버튼 다시 그리기"""
        for w in self.site_frame.winfo_children():
            w.destroy()
        for site in self.sites:
            tk.Button(self.site_frame, text=f"🔗 {site['name']}",
                      bg="#4ECDC4", fg="white", font=("맑은 고딕", 10, "bold"),
                      relief=tk.FLAT, cursor="hand2", anchor=tk.W, padx=10,
                      command=lambda s=site: self.open_site(s)
                      ).pack(fill=tk.X, pady=2, ipady=4)

    @staticmethod
    def _short_path(p):
        s = str(p)
        return "..." + s[-28:] if len(s) > 31 else s

    # ---------- 사이트 관리 ----------
    def open_site(self, site):
        webbrowser.open(site["url"])
        self.log(f"🔗 {site['name']} 열림")

    def add_site(self):
        if len(self.sites) >= MAX_SITES:
            messagebox.showwarning("한도 초과", f"사이트는 최대 {MAX_SITES}개까지 저장할 수 있습니다.\n먼저 삭제 후 추가해주세요.")
            return
        name = simpledialog.askstring("사이트 추가 (1/2)", "사이트 이름을 입력하세요:\n예) 네이버클립", parent=self.root)
        if not name:
            return
        url = simpledialog.askstring("사이트 추가 (2/2)", f"'{name}'의 주소(URL)를 입력하세요:\n예) https://tv.naver.com/", parent=self.root)
        if not url:
            return
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        self.sites.append({"name": name.strip(), "url": url})
        self._save_sites()
        self._render_site_buttons()
        self.log(f"➕ 사이트 추가됨: {name} ({url})")

    def delete_site(self):
        if not self.sites:
            return
        # 삭제 선택 창
        win = tk.Toplevel(self.root)
        win.title("사이트 삭제")
        win.geometry("300x400")
        tk.Label(win, text="삭제할 사이트를 클릭하세요", font=("맑은 고딕", 10, "bold")).pack(pady=8)

        def remove(idx):
            removed = self.sites.pop(idx)
            self._save_sites()
            self._render_site_buttons()
            self.log(f"➖ 삭제됨: {removed['name']}")
            win.destroy()

        for i, site in enumerate(self.sites):
            tk.Button(win, text=f"🗑 {site['name']}", bg="#FFE0E0",
                      relief=tk.FLAT, cursor="hand2", anchor=tk.W, padx=10,
                      command=lambda idx=i: remove(idx)
                      ).pack(fill=tk.X, padx=10, pady=2, ipady=4)
        tk.Button(win, text="취소", command=win.destroy).pack(pady=8)

    # ---------- 공통 ----------
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_box.see(tk.END)

    def _setup_ytdlp(self):
        ok, err = ensure_ytdlp()
        if ok:
            self.ytdlp_ready = True
            self.log("✅ yt-dlp 준비 완료! 이제 다운로드할 수 있습니다.")
        else:
            self.log("❌ yt-dlp 자동 설치 실패:")
            self.log(err[:500])
            self.log("💡 명령 프롬프트(관리자)에서 아래를 실행해주세요:")
            self.log(f'   "{sys.executable}" -m pip install yt-dlp')

    def change_path(self):
        p = filedialog.askdirectory(title="저장 폴더 선택")
        if p:
            self.download_path = Path(p)
            self.path_label.config(text=self._short_path(self.download_path))
            self.log(f"💾 저장 경로 변경: {p}")

    def open_folder(self):
        os.startfile(str(self.download_path))

    @staticmethod
    def clean_url(url):
        url = url.strip()
        url = re.sub(r'^(https?://)+', 'https://', url)
        # 네이버 공유(bridge) 링크면 안에 있는 진짜 주소를 꺼냄
        if "link.naver.com/bridge" in url:
            try:
                from urllib.parse import urlparse, parse_qs, unquote
                qs = parse_qs(urlparse(url).query)
                inner = qs.get("url", [""])[0]
                if inner:
                    url = unquote(inner)
            except Exception:
                pass
        return url

    # ---------- 다운로드 ----------
    def start_download(self):
        url = self.clean_url(self.url_entry.get())
        if not url or url == "https://":
            messagebox.showerror("오류", "URL을 입력해주세요")
            return
        if not self.ytdlp_ready:
            self.log("⏳ yt-dlp 준비 중입니다. 몇 초 후 다시 눌러주세요.")
            return
        self.dl_btn.config(state=tk.DISABLED, text="⏳ 다운로드 중...")
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url):
        try:
            import yt_dlp

            name = self.name_entry.get().strip()
            if name:
                name = re.sub(r'[\\/:*?"<>|]', '_', name)
                out = str(self.download_path / f"{name}.%(ext)s")
            else:
                out = str(self.download_path / "%(title)s.%(ext)s")

            self.log("=" * 55)
            self.log(f"📥 시작: {url}")
            self.log(f"💾 저장: {self.download_path}")

            ydl_opts = {
                "format": "best[ext=mp4]/best",
                "outtmpl": out,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._hook],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                fname = os.path.basename(ydl.prepare_filename(info))

            self.log(f"✅ 완료! 파일: {fname}")
            self.log("=" * 55)
            self.root.after(0, lambda: messagebox.showinfo(
                "성공", f"다운로드 완료!\n\n파일: {fname}\n위치: {self.download_path}"))

        except Exception as e:
            msg = str(e)
            self.log(f"❌ 실패: {msg[:300]}")
            self.root.after(0, lambda: messagebox.showerror("오류", msg[:300]))
        finally:
            self.root.after(0, lambda: self.dl_btn.config(
                state=tk.NORMAL, text="🚀 영상 다운로드 시작"))

    def _hook(self, d):
        if d["status"] == "downloading":
            p = d.get("_percent_str", "?").strip()
            s = d.get("_speed_str", "?").strip()
            try:
                pct = float(p.replace("%", ""))
                if int(pct) % 10 == 0:
                    self.root.after(0, lambda: self.log(f"📊 {p}  ({s})"))
            except Exception:
                pass
        elif d["status"] == "finished":
            self.root.after(0, lambda: self.log("📦 다운로드 완료, 저장 중..."))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
