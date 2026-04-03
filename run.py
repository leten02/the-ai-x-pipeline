#!/usr/bin/env python3
"""
AI 리서치 & 발표자료 자동 생성
================================
그냥 실행하세요 → python3 run.py

모드 1: PDF 신사업 발굴
  → 혁신 AI 기술 논문 PDF를 입력하면
    에이전트 토론으로 최적 도메인을 찾고 신사업 발표자료 생성

모드 2: 주제 리서치
  → 주제를 입력하면 자료 수집 + 토론 + 발표자료 생성
"""

import os
import sys
import subprocess
import re
import keyring
from pathlib import Path

BASE_DIR = Path(__file__).parent
NLM_BIN  = str(BASE_DIR / ".venv/bin/nlm")
PY_BIN   = str(BASE_DIR / ".venv/bin/python3")

BOLD  = "\033[1m"
GREEN = "\033[92m"
BLUE  = "\033[94m"
YELL  = "\033[93m"
RED   = "\033[91m"
DIM   = "\033[2m"
RST   = "\033[0m"

ENV_FILE    = BASE_DIR / ".env"
KEYCHAIN_SERVICE = "ai-pipeline"
KEYCHAIN_KEY     = "ANTHROPIC_API_KEY"


def clear(): print("\033[2J\033[H", end="")

def print_header():
    clear()
    print(f"""
{BLUE}{BOLD}╔══════════════════════════════════════════════════╗
║   AI 신사업 발굴 & 발표자료 자동 생성 파이프라인  ║
║   PDF 논문 → 도메인 토론 → 신사업 발표자료 자동화  ║
╚══════════════════════════════════════════════════╝{RST}
""")

def ask(prompt, default=None, secret=False):
    suffix = f" [{DIM}{default}{RST}]" if default else ""
    try:
        if secret:
            import getpass
            val = getpass.getpass(f"  {prompt}{suffix}: ")
        else:
            val = input(f"  {prompt}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n  {YELL}종료합니다.{RST}\n")
        sys.exit(0)
    return val if val else default

def ok(m):   print(f"  {GREEN}✓{RST} {m}")
def info(m): print(f"  {BLUE}ℹ{RST} {m}")
def warn(m): print(f"  {YELL}!{RST} {m}")
def err(m):  print(f"  {RED}✗{RST} {m}")

def load_env():
    """저장된 .env 불러오기"""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def save_env(env: dict):
    ENV_FILE.write_text(
        "\n".join(f"{k}={v}" for k, v in env.items()),
        encoding="utf-8"
    )

def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ─── STEP 1: NLM 로그인 확인 ────────────────────────────────────
def check_nlm_login() -> bool:
    r = run([NLM_BIN, "auth", "status"])
    return r.returncode == 0

def do_nlm_login():
    print(f"\n  {BOLD}Chrome에서 Google 계정에 로그인되어 있어야 합니다.{RST}")
    input(f"  Chrome이 열려 있으면 Enter를 누르세요... ")
    print(f"\n  {BLUE}로그인 중...{RST}")
    r = subprocess.run([NLM_BIN, "login"], cwd=BASE_DIR)
    if r.returncode == 0:
        ok("NotebookLM 로그인 완료!")
        return True
    else:
        err("로그인 실패. Chrome에서 Google 계정에 로그인 후 다시 시도하세요.")
        return False


# ─── STEP 2: API Key 확인 ────────────────────────────────────────
def check_api_key(env: dict) -> str:
    # 1) 환경변수 (가장 우선)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    # 2) 맥 키체인 (가장 안전)
    try:
        key = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY)
        if key:
            return key
    except Exception:
        pass
    # 3) 구버전 호환: .env 파일
    if env.get("ANTHROPIC_API_KEY"):
        return env["ANTHROPIC_API_KEY"]
    return ""

def ask_api_key(env: dict) -> str:
    print(f"""
  {BOLD}Anthropic API Key가 필요합니다.{RST}
  {DIM}https://console.anthropic.com → API Keys 에서 발급{RST}
""")
    while True:
        key = ask("API Key 입력 (sk-ant-...)", secret=True)
        if key and key.startswith("sk-"):
            # 맥 키체인에 저장 (평문 파일 대신)
            try:
                keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY, key)
                ok("API Key를 맥 키체인에 저장했어요 (다음부터 안 물어봐요)")
                # 구버전 .env에 키가 있었으면 제거
                if "ANTHROPIC_API_KEY" in env:
                    del env["ANTHROPIC_API_KEY"]
                    save_env(env)
            except Exception:
                # 키체인 실패 시 .env에 저장
                save_pref = ask(".env 파일에 저장할까요? (y/n)", default="y")
                if save_pref and save_pref.lower() == "y":
                    env["ANTHROPIC_API_KEY"] = key
                    save_env(env)
                    ok("API Key 저장됨 (.env)")
            return key
        else:
            warn("올바른 API Key 형식이 아니에요. 'sk-ant-'로 시작해야 합니다.")


# ─── STEP 3: 옵션 선택 ──────────────────────────────────────────
def ask_options() -> dict:
    print(f"""
  {BOLD}── 옵션 (기본값으로 바로 시작하려면 그냥 Enter) ──{RST}
  {DIM}AI가 자동으로 혁신 기술을 분석하고 최적 신사업 도메인을 찾아냅니다{RST}
""")

    # 라운드 수
    rounds_str = ask("AI 토론 라운드 수", default="3")
    try:
        rounds = int(rounds_str)
        rounds = max(1, min(rounds, 5))
    except (ValueError, TypeError):
        rounds = 3

    # 검색 모드
    print(f"""
  웹 검색 모드:
    {GREEN}1{RST}) 빠른 검색 (30초, 약 10개 소스)  ← 기본
    {BLUE}2{RST}) 깊은 검색 (5분, 약 40개 소스)
    {YELL}3{RST}) NLM 없이 Claude만 사용 (로그인 불필요)
""")
    mode_input = ask("선택", default="1")
    if mode_input == "2":
        nlm_mode, no_nlm = "deep", False
    elif mode_input == "3":
        nlm_mode, no_nlm = "fast", True
    else:
        nlm_mode, no_nlm = "fast", False

    return {
        "rounds":  rounds,
        "mode":    nlm_mode,
        "no_nlm":  no_nlm,
    }


# ─── STEP 4: 실행 ────────────────────────────────────────────────
def run_pipeline(opts: dict, api_key: str):
    print(f"""
{GREEN}{BOLD}╔══════════════════════════════════════════════════╗
║  파이프라인 시작!                                ║
║  AI가 혁신 기술 분석 → 도메인 토론 → 신사업 발굴  ║
╚══════════════════════════════════════════════════╝{RST}
  라운드 : {opts['rounds']}라운드 토론
  검색   : {'NLM 웹 검색 (' + opts['mode'] + ')' if not opts['no_nlm'] else 'Claude만 사용'}
""")

    cmd = [
        PY_BIN, str(BASE_DIR / "pipeline.py"),
        "--innovative-ai",          # 혁신 AI 신사업 발굴 모드
        "--rounds", str(opts["rounds"]),
        "--mode",   opts["mode"],
    ]
    if opts["no_nlm"]:
        cmd.append("--no-nlm")

    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = api_key

    # 실시간 출력
    proc = subprocess.Popen(cmd, env=env, cwd=BASE_DIR)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print(f"\n  {YELL}중단됨.{RST}")
        return False

    return proc.returncode == 0


# ─── STEP 5: 결과 안내 ───────────────────────────────────────────
def open_result():
    print(f"""
  {GREEN}✓{RST} 파이프라인 완료!

  {BOLD}확인 방법:{RST}
  {GREEN}📑{RST} 슬라이드  → {BOLD}notebooklm.google.com{RST} 접속 후 노트북 확인
  {GREEN}🌐{RST} 토론 뷰어 → output/ 폴더의 HTML 파일
  {GREEN}💬{RST} 토론 내용 → output/ 폴더의 .txt 파일
""")


# ─── 메인 ────────────────────────────────────────────────────────
def main():
    print_header()

    env = load_env()

    # ── NLM 로그인 ──
    print(f"  {BOLD}[1/3] NotebookLM 로그인 확인{RST}")
    if check_nlm_login():
        ok("이미 로그인되어 있어요")
    else:
        warn("NotebookLM에 로그인이 필요합니다")
        if not do_nlm_login():
            info("NLM 없이 계속 진행할게요 (--no-nlm 모드 사용)")
            env["SKIP_NLM"] = "1"

    # ── API Key ──
    print(f"\n  {BOLD}[2/3] Anthropic API Key 확인{RST}")
    api_key = check_api_key(env)
    if api_key:
        masked = api_key[:10] + "..." + api_key[-4:]
        ok(f"API Key 확인됨: {DIM}{masked}{RST}")
    else:
        api_key = ask_api_key(env)

    # ── 주제 & 옵션 ──
    print(f"\n  {BOLD}[3/3] 발표 주제 설정{RST}")
    opts = ask_options()

    # NLM 스킵이면 강제
    if env.get("SKIP_NLM") == "1":
        opts["no_nlm"] = True

    # ── 최종 확인 ──
    print(f"""
{BLUE}{'─'*52}{RST}
  모드   : {BOLD}혁신 AI 신사업 자동 발굴{RST}
  라운드 : {opts['rounds']}라운드 토론
  검색   : {'NLM 웹 검색 (' + opts['mode'] + ')' if not opts['no_nlm'] else 'Claude만 사용'}
{BLUE}{'─'*52}{RST}
""")
    go = ask("시작할까요? (y/n)", default="y")
    if go and go.lower() == "n":
        print(f"\n  취소됐습니다.\n")
        sys.exit(0)

    # ── 실행 ──
    success = run_pipeline(opts, api_key)

    # ── 결과 열기 ──
    if success:
        open_result()
    else:
        err("파이프라인 실행 중 오류가 발생했습니다.")
        info(f"output/ 폴더를 확인하세요: {BASE_DIR / 'output'}")

    # ── 다시 실행? ──
    print()
    again = ask("다시 실행할까요? (y/n)", default="n")
    if again and again.lower() == "y":
        main()
    else:
        print(f"\n  {GREEN}완료! output/ 폴더에서 결과물을 확인하세요.{RST}\n")


if __name__ == "__main__":
    main()
