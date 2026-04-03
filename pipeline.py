#!/usr/bin/env python3
"""
범용 AI 리서치 & 발표자료 자동 생성 파이프라인
===============================================
사용법:
    python3 pipeline.py "주제"
    python3 pipeline.py "The AI Vet" --rounds 2 --lang ko
    python3 pipeline.py "전기차 배터리 기술" --mode deep

파이프라인:
    Phase 1  → Claude: 주제 분석, 검색 쿼리 & 프레임워크 생성
    Phase 2  → NLM: 웹 자동 검색 + 소스 수집 + 브리핑 리포트
    Phase 3  → Agent 토론 (N라운드 반복, 이전 결과 기반 개선)
               Round 1: 리서치 품질 검토 & 갭 분석
               Round 2: 기회 vs 리스크 전략 토론
               Round 3: 발표 구조 설계 토론
    Phase 4  → Synthesis Agent: 토론 결과 → 발표 슬라이드 설계
    Phase 5  → NotebookLM 슬라이드 생성
"""

import os
import re
import sys
import json
import time
import textwrap
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError as e:
    sys.exit(f"[ERROR] 패키지 없음: {e}\n실행: .venv/bin/pip install anthropic")

# ─────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
NLM_BIN    = str(BASE_DIR / ".venv/bin/nlm")

BOLD = "\033[1m"; GREEN = "\033[92m"; BLUE = "\033[94m"
YELL = "\033[93m"; RED = "\033[91m"; DIM = "\033[2m"; RST = "\033[0m"

# 에이전트별 터미널 색상
AGENT_COLORS = {
    "Researcher":      ("\033[92m", "🔬"),   # 초록
    "Devil":           ("\033[91m", "😈"),   # 빨강
    "Optimist":        ("\033[96m", "🚀"),   # 시안
    "Risk":            ("\033[93m", "⚠️ "),   # 노랑
    "Strategist":      ("\033[94m", "🎯"),   # 파랑
    "Domain":          ("\033[95m", "🏛️ "),   # 보라
    "Audience":        ("\033[96m", "👥"),   # 시안
    "Synthesizer":     ("\033[94m", "🔗"),   # 파랑
    "Moderator":       ("\033[97m", "⚖️ "),   # 흰색
}

def get_agent_style(agent_name: str):
    for key, (color, emoji) in AGENT_COLORS.items():
        if key in agent_name:
            return color, emoji
    return "\033[97m", "🤖"

def print_agent_speech(agent_name: str, content: str):
    """에이전트 발언을 터미널에 예쁘게 전체 출력"""
    color, emoji = get_agent_style(agent_name)
    width = 60
    sep = "─" * width
    print(f"\n  {color}{BOLD}{sep}{RST}")
    print(f"  {color}{emoji} {BOLD}{agent_name}{RST}")
    print(f"  {color}{sep}{RST}")
    # 긴 텍스트 줄바꿈 처리
    for line in content.split("\n"):
        wrapped = textwrap.wrap(line, width=width - 2) or [""]
        for wline in wrapped:
            print(f"  {wline}")
    print(f"  {color}{sep}{RST}")

# ─────────────────────────────────────────────────────────────────
# CLI 인수 파싱
# ─────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="AI 리서치 & 발표자료 자동 생성 파이프라인")
    p.add_argument("topic", nargs="?", default="",
                   help="분석할 주제 (--innovative-ai 모드에서는 생략)")
    p.add_argument("--innovative-ai", action="store_true",
                   help="혁신 AI 기술 기반 신사업 자동 발굴 모드")
    p.add_argument("--pdf",     nargs="+", metavar="FILE",
                   help="AI 기술 논문 PDF 경로 (옵션)")
    p.add_argument("--rounds",  type=int, default=2, help="토론 라운드 수 (기본 2)")
    p.add_argument("--lang",    default="ko",        help="NLM 리포트 언어 (기본 ko)")
    p.add_argument("--mode",    default="fast",      choices=["fast","deep"],
                   help="NLM 웹 검색 모드: fast(30초) / deep(5분)")
    p.add_argument("--no-nlm",  action="store_true", help="NLM 없이 Claude만 사용")
    p.add_argument("--out",     default="output",    help="출력 디렉토리")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────
def banner(n, title):
    line = "─" * 62
    print(f"\n{BOLD}{BLUE}{line}\n  Phase {n}: {title}\n{line}{RST}")

def ok(m):   print(f"  {GREEN}✓{RST} {m}")
def info(m): print(f"  {BLUE}ℹ{RST} {m}")
def warn(m): print(f"  {YELL}⚠{RST} {m}")

def run_nlm(*args, inp=None, timeout=600):
    cmd = [NLM_BIN] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       input=inp, cwd=BASE_DIR, timeout=timeout)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def strip_ansi(s):
    return re.sub(r'\x1b\[[0-9;]*m', '', s)

def safe_json(raw: str) -> dict:
    """JSON 파싱 — 잘린 경우 닫힘 괄호를 보정해서 재시도"""
    # 1) 그대로 파싱
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 2) 코드블록 제거 후 재시도
    clean = re.sub(r'^```[a-z]*\n?', '', raw.strip(), flags=re.MULTILINE)
    clean = re.sub(r'```$', '', clean.strip())
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # 3) { ... } 추출
    m = re.search(r'\{.*\}', clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # 4) 잘린 JSON 보정 — 열린 괄호 수만큼 닫기
    snippet = m.group() if m else clean
    open_b  = snippet.count('{') - snippet.count('}')
    open_sq = snippet.count('[') - snippet.count(']')
    fixed   = snippet.rstrip().rstrip(',')
    fixed  += ']' * max(0, open_sq) + '}' * max(0, open_b)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return {}

def claude_call(client, system, messages, max_tokens=1500):
    r = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return r.content[0].text.strip()


# ═══════════════════════════════════════════════════════════════════
# Phase 0: PDF 텍스트 추출 (PDF 모드 전용)
# ═══════════════════════════════════════════════════════════════════
def phase0_extract_pdfs(pdf_paths: list[str]) -> str:
    """PDF 파일에서 텍스트 추출 → 합쳐서 반환"""
    banner(0, "PDF 논문 분석")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit(f"{RED}[ERROR]{RST} PyMuPDF 없음. 실행: .venv/bin/pip install pymupdf")

    combined = ""
    for path in pdf_paths:
        p = Path(path)
        if not p.exists():
            warn(f"파일 없음: {path}")
            continue
        info(f"읽는 중: {p.name}")
        doc = fitz.open(str(p))
        text = ""
        for page in doc[:12]:          # 최대 12페이지
            text += page.get_text()
        combined += f"\n\n{'='*60}\n논문: {p.name}\n{'='*60}\n{text[:4000]}"
        ok(f"{p.name} ({len(doc)}쪽, {len(text)}자 추출)")

    if not combined:
        sys.exit(f"{RED}[ERROR]{RST} 추출된 텍스트 없음. PDF 경로를 확인하세요.")

    ok(f"총 {len(combined)}자 추출 완료")
    return combined


# ═══════════════════════════════════════════════════════════════════
# 혁신 AI 기술 지식 (논문 3편 핵심 요약 — 프롬프트 내장)
# ═══════════════════════════════════════════════════════════════════
INNOVATIVE_AI_KNOWLEDGE = """
방향성 요약 (참고용):
- AI가 과학적 발견 프로세스 자체를 자동화하는 시대 (가설→실험→검증→논문 루프)
- 물리 세계와 연결된 자율 실험실 (AI + 로봇 + 센서가 실험을 스스로 수행)
- 멀티모달 에이전트가 지식을 해석하는 것을 넘어 직접 행동하는 "Lab-pilot" 전환
- 핵심 키워드: Agentic AI, Self-Driving Lab, Open-Ended Discovery, Scientific Automation
"""


# ═══════════════════════════════════════════════════════════════════
# Phase 1 (혁신 AI 모드): 신사업 도메인 후보 자동 도출
# ═══════════════════════════════════════════════════════════════════
def phase1_innovative_ai(client) -> dict:
    banner(1, "The AI [X] 신사업 도메인 발굴")

    system = textwrap.dedent("""
        당신은 세계 최고의 스타트업 발굴 전문가입니다.
        세상의 다양한 산업에서 사람들이 겪는 진짜 문제를 찾고,
        거기에 "The AI [X]" 형태의 AI 솔루션 사업 기회를 발굴하세요.

        참고: "The AI Vet"처럼 특정 직군/역할을 AI로 대체/강화하는 사업 모델.
        예시: The AI Vet(반려동물 수의사), The AI Lawyer(법률), The AI Farmer(농업)

        반환 형식 (JSON만, 코드블록 없이):
        {
          "candidate_domains": [
            {
              "domain": "도메인명 (예: 반려동물 의료)",
              "service_name": "The AI [X] 형식의 서비스명",
              "pain_point": "이 도메인에서 사람들이 실제로 겪는 가장 심각한 문제",
              "why_ai": "왜 기존 방식으로는 해결 안 되고 AI만 가능한지",
              "market_size": "글로벌 시장 규모 ($)",
              "target_customer": "주요 타겟 고객",
              "example_company": "유사 방향의 기존 기업 (없으면 None)"
            }
          ],
          "nlm_search_queries": ["시장 조사용 영어 검색 쿼리 4개"],
          "nlm_queries": ["NLM notebook 한국어 질의 4개"]
        }

        candidate_domains는 반드시 10개. 최대한 다양한 산업에서 선정하세요.
        연구/과학 도메인 제외. 일상생활, 전문직, 중소기업, 헬스케어, 교육, 농업, 물류,
        금융, 부동산, 법률, 복지, 환경 등 실제 사람들의 삶과 직결된 분야에서 선정하세요.
        반드시 JSON만 반환하세요.
    """).strip()

    user_msg = """
세상에는 아직 AI가 제대로 해결하지 못한 문제들이 많습니다.
특히 전문가 접근이 어렵거나 비용이 비싸거나 지역 격차가 심한 분야에서
AI가 게임체인저가 될 수 있습니다.

지금 당장 "The AI [직군/역할]" 형태로 사업화할 수 있는 도메인 10개를 찾아주세요.

조건:
- 실제 사람들이 돈을 낼 만큼 심각한 문제가 있는 분야
- 기존 해결책이 부족하거나 비싸거나 접근하기 어려운 영역
- AI 에이전트/멀티모달/자율 추론 기술로 실질적 해결이 가능한 분야
- 연구소나 학술 도메인 제외, 실생활/비즈니스 현장 중심
- 서로 다른 산업군에서 골고루 선정할 것
- 2025년 기준 바로 시작할 수 있는 분야 우선
"""

    info("Claude가 신사업 도메인 발굴 중...")
    raw = claude_call(client, system, [{"role": "user", "content": user_msg}], max_tokens=4500)

    frame = safe_json(raw)

    domains = frame.get("candidate_domains", [])
    print(f"\n  {BOLD}후보 도메인 {len(domains)}개:{RST}")
    for i, d in enumerate(domains, 1):
        print(f"  {GREEN}{i}.{RST} {BOLD}{d.get('service_name', d.get('domain',''))}{RST}")
        print(f"     문제: {d.get('pain_point','')[:60]}...")
        print(f"     시장: {d.get('market_size','?')} | AI 적합성: {d.get('why_ai','')[:50]}...")

    return frame


# ═══════════════════════════════════════════════════════════════════
# Phase 2: 10개 아이디어 토론 → 최고 아이디어 선정
# ═══════════════════════════════════════════════════════════════════
def phase2_idea_debate(client, frame: dict) -> dict:
    """10개 아이디어를 에이전트 토론으로 검토, 최고 아이디어 1개 선정"""
    banner(2, "10개 아이디어 토론 — 최고 아이디어 선정")

    memory = DebateMemory()
    domains = frame.get("candidate_domains", [])

    idea_list = "\n".join(
        f"[{i+1}] {d.get('service_name', d.get('domain',''))}: "
        f"{d.get('pain_point','')[:80]} "
        f"(시장: {d.get('market_size','?')})"
        for i, d in enumerate(domains)
    )

    # ── 라운드 1: 각 아이디어 챔피언 토론 ──
    print(f"\n  {BOLD}── 라운드 1: 아이디어 챔피언 토론 ──{RST}")

    # 아이디어를 3그룹으로 나눠 각 챔피언이 담당
    group_size = len(domains) // 3
    groups = [domains[:group_size], domains[group_size:group_size*2], domains[group_size*2:]]

    for i, group in enumerate(groups):
        ideas = "\n".join(
            f"  - {d.get('service_name', d.get('domain',''))}: {d.get('pain_point','')[:60]}"
            for d in group
        )
        resp = run_agent(client, f"Champion {i+1} (아이디어 챔피언 {i+1})",
            f"담당 아이디어들의 열렬한 지지자. 시장 기회와 AI 적합성을 가장 잘 아는 전문가",
            f"다음 아이디어들 중 가장 잠재력 있는 것을 골라 강력히 주장하세요:\n{ideas}\n\n"
            f"왜 이 아이디어가 다른 모든 아이디어보다 우월한지 구체적 근거를 제시하세요:\n"
            f"- 문제의 심각성과 시장 규모\n"
            f"- AI로 해결 가능한 이유\n"
            f"- 경쟁 우위\n"
            f"전체 아이디어 목록:\n{idea_list}",
            memory, max_tokens=600)
        print_agent_speech(f"Champion {i+1} (아이디어 챔피언 {i+1})", resp)

    # ── 라운드 2: 비판 & 필터링 ──
    print(f"\n  {BOLD}── 라운드 2: 비판 & 필터링 ──{RST}")

    resp = run_agent(client, "Market Critic (시장 비평가)",
        "VC 투자자. 수백 개 스타트업을 본 눈으로 아이디어의 시장성을 냉정하게 평가",
        f"챔피언들이 주장한 아이디어들을 투자자 관점에서 냉정하게 평가하세요:\n"
        f"- 실제로 돈이 되는 아이디어 vs 그냥 멋있어 보이는 아이디어\n"
        f"- 진입 장벽이 낮아서 금방 카피당할 아이디어\n"
        f"- 규제/윤리 리스크가 큰 아이디어\n"
        f"가장 유망한 Top 3를 선정하고 이유를 설명하세요.\n\n"
        f"전체 아이디어:\n{idea_list}",
        memory, max_tokens=700)
    print_agent_speech("Market Critic (시장 비평가)", resp)

    resp = run_agent(client, "Innovative AI Agent (혁신 AI 전문가)",
        "최첨단 AI 기술을 가장 잘 아는 전문가. 어떤 아이디어가 AI로 가장 강력해질 수 있는지 판단",
        f"AI 기술 관점에서 10개 아이디어를 평가하세요:\n"
        f"- 멀티에이전트/자율 추론/피드백 루프로 기존 대비 10배 임팩트를 낼 수 있는 아이디어\n"
        f"- 아무도 시도하지 않은 방식으로 AI를 적용할 수 있는 아이디어\n"
        f"- 데이터 플라이휠 효과로 시간이 갈수록 강해지는 아이디어\n"
        f"AI 혁신 잠재력 기준 Top 3를 선정하고 이유를 설명하세요.\n\n"
        f"전체 아이디어:\n{idea_list}",
        memory, max_tokens=700)
    print_agent_speech("Innovative AI Agent (혁신 AI 전문가)", resp)

    # ── 라운드 3: 최종 선정 ──
    print(f"\n  {BOLD}── 라운드 3: 최종 선정 ──{RST}")

    resp = run_agent(client, "Selector (최종 선정자)",
        "모든 토론을 종합하여 단 하나의 최고 아이디어를 선정하는 총책임자",
        f"지금까지 토론을 종합하여 최종 아이디어 1개를 선정하세요.\n\n"
        f"선정 기준 (우선순위 순):\n"
        f"1. 문제의 심각성 — 사람들이 실제로 돈을 낼 만큼 아픈 문제인가?\n"
        f"2. AI 차별성 — AI가 아니면 해결 불가능한 방식인가?\n"
        f"3. 시장 규모 — 충분히 큰 시장인가?\n"
        f"4. 실행 가능성 — 지금 당장 시작할 수 있는가?\n\n"
        f"반드시 아이디어 번호와 서비스명을 명시하고, 선정 이유를 3줄로 요약하세요.\n\n"
        f"전체 아이디어:\n{idea_list}",
        memory, max_tokens=500)
    print_agent_speech("Selector (최종 선정자)", resp)
    memory.add_conclusion(resp)

    # 선정된 아이디어를 frame에서 찾아 반환
    # Selector 답변에서 번호 파싱 시도
    selected = domains[0]  # 기본값
    for i, d in enumerate(domains):
        num = str(i + 1)
        svc = d.get('service_name', d.get('domain', ''))
        if f"[{num}]" in resp or svc in resp:
            selected = d
            break

    frame["selected_domain"] = selected
    ok(f"선정된 아이디어: {BOLD}{selected.get('service_name', selected.get('domain',''))}{RST}")
    ok(f"문제: {selected.get('pain_point','')[:60]}")

    return frame


# ═══════════════════════════════════════════════════════════════════
# Phase 1 (PDF 모드): AI 기술 분석 → 도메인 후보 도출
# ═══════════════════════════════════════════════════════════════════
def phase1_pdf_mode(client, pdf_texts: str) -> dict:
    banner(1, "AI 기술 분석 & 도메인 후보 도출")

    system = textwrap.dedent("""
        당신은 세계 최고의 기술 벤처 전략가입니다.
        제공된 AI 기술 논문들을 분석하여 신사업 발굴 프레임워크를 JSON으로 반환하세요.

        반환 형식 (JSON만, 코드블록 없이):
        {
          "ai_technologies": [
            {"name": "기술명", "capability": "이 기술이 할 수 있는 것", "maturity": "현재 성숙도"}
          ],
          "key_insight": "이 AI 기술들의 핵심 공통점 한 줄",
          "candidate_domains": [
            {
              "domain": "도메인명 (예: 신약개발, 배터리소재, 농업, 탄소포집)",
              "why_fit": "이 AI 기술이 이 도메인에 특히 잘 맞는 이유",
              "market_size": "예상 시장 규모 (달러)",
              "pain_point": "현재 이 도메인의 가장 큰 문제"
            }
          ],
          "nlm_search_queries": ["시장 조사용 영어 검색 쿼리 4개"],
          "nlm_queries": ["NLM notebook query 한국어 질문 4개"],
          "debate_focus": "토론에서 집중할 핵심 질문",
          "target_audience": "발표 대상"
        }

        candidate_domains는 반드시 4~5개. 다양한 산업군에서 선택하세요.
        반드시 JSON만 반환하세요. 코드블록 없이.
    """).strip()

    user_msg = f"다음 AI 기술 논문들을 분석하여 신사업 도메인을 발굴하세요:\n\n{pdf_texts[:6000]}"

    info("Claude가 AI 기술 분석 및 도메인 후보 도출 중...")
    raw = claude_call(client, system, [{"role": "user", "content": user_msg}], max_tokens=3000)

    frame = safe_json(raw)

    techs = frame.get("ai_technologies", [])
    domains = frame.get("candidate_domains", [])
    ok(f"AI 기술 {len(techs)}개 식별")
    ok(f"핵심 인사이트: {frame.get('key_insight', '')}")
    ok(f"후보 도메인 {len(domains)}개 도출:")
    for d in domains:
        print(f"    • {d.get('domain','')}: {d.get('why_fit','')[:50]}...")

    return frame


# ═══════════════════════════════════════════════════════════════════
# Phase 1: 주제 분석 — Claude가 검색 전략 & 프레임워크 생성
# ═══════════════════════════════════════════════════════════════════
def phase1_analyze(client, topic: str) -> dict:
    banner(1, f"주제 분석: '{topic}'")

    system = textwrap.dedent("""
        당신은 세계 최고의 리서치 전략가입니다.
        주어진 주제에 대해 다음을 JSON으로 반환하세요:
        {
          "korean_title": "한국어 주제명",
          "english_title": "English topic",
          "one_line": "주제를 한 줄로 설명",
          "core_questions": ["핵심 질문 4개"],
          "nlm_search_queries": ["NLM 웹검색에 쓸 영어 쿼리 3개"],
          "nlm_queries": ["NLM notebook query에 쓸 한국어 질문 5개"],
          "debate_topics": [
            {"topic": "토론 주제 1", "angle": "어떤 관점에서 토론할지"},
            {"topic": "토론 주제 2", "angle": "어떤 관점에서 토론할지"},
            {"topic": "토론 주제 3", "angle": "어떤 관점에서 토론할지"}
          ],
          "slide_sections": ["예상 발표 섹션명 6~8개"],
          "target_audience": "예상 발표 대상"
        }
        반드시 JSON만 반환하세요. 코드블록 없이.
    """).strip()

    info("Claude가 주제 분석 및 검색 전략 수립 중...")
    raw = claude_call(client, system, [{"role":"user","content":f"주제: {topic}"}], max_tokens=2500)

    frame = safe_json(raw)

    ok(f"한국어 제목: {frame.get('korean_title', topic)}")
    ok(f"핵심 질문 {len(frame.get('core_questions',[]))}개 도출")
    ok(f"NLM 검색 쿼리 {len(frame.get('nlm_search_queries',[]))}개 생성")
    ok(f"토론 주제 {len(frame.get('debate_topics',[]))}개 설계")

    return frame


# ═══════════════════════════════════════════════════════════════════
# Phase 2: NLM 웹 자동 검색 + 리포트
# ═══════════════════════════════════════════════════════════════════
def phase2_nlm(topic: str, frame: dict, mode: str, lang: str) -> tuple[str, dict]:
    banner(2, "NotebookLM 웹 자동 검색 & 분석")

    nb_title = f"{frame.get('korean_title', topic)} 리서치 {datetime.now().strftime('%m%d_%H%M')}"

    # ── 노트북 생성 ──
    info("노트북 생성 중...")
    out, err, rc = run_nlm("notebook", "create", nb_title)
    if rc != 0:
        warn(f"노트북 생성 실패: {err}")
        return "", {}

    m = re.search(r"ID:\s*(\S+)", out)
    if not m:
        warn(f"Notebook ID 파싱 실패: {out}")
        return "", {}
    nb_id = m.group(1)
    ok(f"노트북 ID: {DIM}{nb_id}{RST}")

    # ── 웹 자동 검색 (검색 쿼리별) ──
    search_queries = frame.get("nlm_search_queries", [topic])
    for q in search_queries[:3]:
        info(f"웹 검색 시작: '{q}' (mode={mode})")
        out, err, rc = run_nlm(
            "research", "start", q,
            "--source", "web",
            "--mode", mode,
            "--notebook-id", nb_id,
        )
        if rc == 0:
            ok(f"검색 시작됨: {q}")
        else:
            warn(f"검색 실패 (건너뜀): {err[:80]}")
        time.sleep(2)

    # ── 검색 완료 대기 ──
    wait_time = 300 if mode == "fast" else 600
    info(f"웹 검색 완료 대기 중 (최대 {wait_time}초)...")
    out, err, rc = run_nlm(
        "research", "status", nb_id,
        "--max-wait", str(wait_time),
        "--poll-interval", "30"
    )
    if rc == 0:
        ok("검색 완료")
    else:
        warn("검색 상태 확인 실패 (계속 진행)")

    # ── 검색 결과 임포트 ──
    info("발견된 소스 임포트 중...")
    out, err, rc = run_nlm("research", "import", nb_id)
    if rc == 0:
        ok("소스 임포트 완료")
    else:
        warn(f"임포트 실패: {err[:80]}")

    # ── 추가 텍스트 소스 (주제 기반 정보) ──
    extra_text = f"주제: {frame.get('korean_title', topic)}\n핵심 질문:\n"
    for q in frame.get("core_questions", []):
        extra_text += f"- {q}\n"
    run_nlm("source", "add", nb_id, "--text", extra_text, "--title", "연구 프레임워크")

    time.sleep(10)

    # ── NLM 질의 ──
    research_data = {}
    nlm_queries = frame.get("nlm_queries", [
        f"{topic}의 핵심 문제와 시장 기회를 요약해줘",
        f"{topic}의 경쟁 환경과 차별화 전략은?",
        f"{topic}의 기술적 구현 방법과 과제는?",
        f"{topic}의 비즈니스 모델과 수익화 방안은?",
        f"{topic}의 리스크와 극복 방안은?",
    ])

    for q in nlm_queries[:5]:
        info(f"NLM 질의: {q[:55]}...")
        out, err, rc = run_nlm("notebook", "query", nb_id, q)
        if rc == 0 and out:
            key = f"q{len(research_data)+1}"
            research_data[key] = {"question": q, "answer": strip_ansi(out)}
            ok(f"답변 수집 ({len(strip_ansi(out))}자)")
        time.sleep(4)

    # ── Briefing Doc 생성 ──
    info("Briefing Doc 생성 중...")
    out, err, rc = run_nlm(
        "report", "create", nb_id,
        "--format", "Briefing Doc",
        "--language", lang,
        "--confirm"
    )
    if rc == 0:
        research_data["briefing"] = strip_ansi(out)
        ok("Briefing Doc 완료")
    else:
        warn(f"Briefing Doc 실패: {err[:80]}")
        research_data["briefing"] = ""

    return nb_id, research_data


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Multi-Agent 토론 (이전 결과 기반 반복 개선)
# ═══════════════════════════════════════════════════════════════════
class DebateMemory:
    """에이전트들의 공유 메모리 — 이전 발언을 다음 에이전트가 읽는다"""
    def __init__(self):
        self.turns: list[dict] = []       # {"agent", "role", "content"}
        self.conclusions: list[str] = []  # 라운드별 핵심 결론

    def add(self, agent: str, role: str, content: str):
        self.turns.append({"agent": agent, "role": role, "content": content})

    def last_n(self, n=4) -> str:
        recent = self.turns[-n:]
        return "\n\n".join(f"[{t['agent']}]: {t['content']}" for t in recent)

    def add_conclusion(self, c: str):
        self.conclusions.append(c)

    def all_conclusions(self) -> str:
        return "\n".join(f"- {c}" for c in self.conclusions)


def run_agent(client, agent_name: str, role_desc: str,
              task: str, memory: DebateMemory, max_tokens=600) -> str:
    """단일 에이전트 실행 — 공유 메모리 기반"""
    system = textwrap.dedent(f"""
        당신은 '{agent_name}'입니다.
        역할: {role_desc}

        지금까지 토론 맥락 (반드시 참고):
        {memory.last_n(4)}

        규칙:
        - 이전 발언을 비판적으로 검토하고 새로운 관점을 추가하세요
        - 반복은 금지. 새로운 근거나 각도로 발전시키세요
        - 한국어로 명확하고 간결하게 (300자 이내)
    """).strip()

    response = claude_call(client, system,
                           [{"role": "user", "content": task}],
                           max_tokens=max_tokens)
    memory.add(agent_name, role_desc, response)
    return response


def phase3_debate(client, topic: str, frame: dict,
                  research_data: dict, rounds: int) -> tuple[DebateMemory, list]:
    banner(3, f"Multi-Agent 토론 ({rounds}라운드)")

    memory = DebateMemory()
    debate_topics = frame.get("debate_topics", [
        {"topic": f"{topic}의 핵심 가치", "angle": "기회와 리스크"},
        {"topic": f"{topic}의 실행 전략", "angle": "단기 vs 장기"},
        {"topic": f"{topic}의 발표 구조", "angle": "청중 관점에서"},
    ])

    # NLM 연구 요약 (컨텍스트)
    research_summary = "\n".join([
        f"Q: {v['question']}\nA: {v['answer'][:300]}"
        for k, v in research_data.items()
        if isinstance(v, dict) and "question" in v
    ])[:1500]
    if research_data.get("briefing"):
        research_summary += f"\n\n[Briefing]\n{research_data['briefing'][:500]}"

    all_round_results = []

    for round_num in range(1, rounds + 1):
        print(f"\n  {BOLD}── 라운드 {round_num} ──{RST}")

        # ── 라운드 1: 리서치 검토 & 갭 분석
        if round_num == 1:
            round_results = _round_research_review(
                client, memory, topic, research_summary, debate_topics
            )

        # ── 라운드 2: 전략 토론
        elif round_num == 2:
            round_results = _round_strategy_debate(
                client, memory, topic, debate_topics
            )

        # ── 추가 라운드: 자유 토론 + 심화
        else:
            round_results = _round_freeform(
                client, memory, topic, round_num, debate_topics
            )

        all_round_results.append(round_results)

    # ── 최종 합의: Moderator가 토론 전체 종합
    print(f"\n  {BOLD}── 최종 합의 ──{RST}")
    moderator_conclusion = run_agent(
        client,
        "Moderator (종합 분석가)",
        "모든 에이전트의 토론을 종합하여 핵심 결론과 발표 방향을 도출하는 역할",
        textwrap.dedent(f"""
            지금까지의 전체 토론을 바탕으로 다음을 작성하세요:
            1. 토론에서 합의된 핵심 인사이트 3가지
            2. 발표 시 반드시 포함해야 할 강력한 포인트 3가지
            3. 청중이 가장 궁금해할 질문과 답변 1가지
            주제: {topic}
        """).strip(),
        memory, max_tokens=800
    )

    print_agent_speech("Moderator (종합 분석가)", moderator_conclusion)

    memory.add_conclusion(moderator_conclusion)
    return memory, all_round_results


def _round_research_review(client, memory, topic, research_summary, debate_topics):
    """라운드 1: 리서치 품질 검토"""
    results = {}

    # Agent 1: Researcher — 핵심 발견 정리
    researcher_task = f"""
주제 '{topic}'에 대해 수집된 리서치를 분석하세요:
{research_summary}

발견한 핵심 사실과 데이터를 3가지로 정리하고,
이 주제의 가장 강력한 근거가 되는 포인트를 제시하세요.
"""
    resp = run_agent(client, "Researcher (리서치 분석가)",
                     "수집된 데이터를 분석하여 핵심 인사이트를 도출하는 전문가",
                     researcher_task, memory)
    results["researcher"] = resp
    print_agent_speech("Researcher (리서치 분석가)", resp)

    # Agent 2: Devil's Advocate — 리서치 갭 지적
    devil_task = f"""
Researcher의 분석을 검토하세요. 주제: '{topic}'
다음을 날카롭게 지적하세요:
- 리서치에서 빠진 중요한 관점이나 데이터
- 제시된 근거의 약점
- 실제 현장에서 맞닥뜨릴 반론
"""
    resp = run_agent(client, "Devil's Advocate (비판적 검토자)",
                     "주장의 약점과 빠진 관점을 날카롭게 지적하는 비판적 사고자",
                     devil_task, memory)
    results["devil"] = resp
    print_agent_speech("Devil's Advocate (비판적 검토자)", resp)

    # Agent 3: Researcher (개선) — 갭 보완
    improve_task = f"""
Devil's Advocate의 지적을 반영하여 분석을 강화하세요.
- 지적된 갭을 어떻게 보완할 것인지
- 발표 시 이 약점을 어떻게 선제적으로 다룰지
- 보강된 핵심 메시지는 무엇인지
"""
    resp = run_agent(client, "Researcher (개선된 분석)",
                     "비판을 수용하여 더 강력한 분석을 만드는 연구자",
                     improve_task, memory)
    results["researcher_v2"] = resp
    print_agent_speech("Researcher (개선된 분석)", resp)

    return results


def _round_strategy_debate(client, memory, topic, debate_topics):
    """라운드 2: 기회 vs 리스크 전략 토론"""
    results = {}

    # Agent 4: Optimist — 최적 기회
    opt_task = f"""
주제 '{topic}'에서 가장 강력한 기회와 성공 시나리오를 제시하세요.
구체적인 수치, 사례, 타임라인을 포함하세요.
이전 라운드 인사이트를 기반으로 발전시키세요.
"""
    resp = run_agent(client, "Optimist (기회 분석가)",
                     "최선의 시나리오와 기회를 구체적 근거와 함께 제시하는 전략가",
                     opt_task, memory)
    results["optimist"] = resp
    print_agent_speech("Optimist (기회 분석가)", resp)

    # Agent 5: Risk Analyst — 핵심 리스크
    risk_task = f"""
주제 '{topic}'의 핵심 리스크 3가지를 분석하세요.
각 리스크별 발생 가능성, 영향도, 대응 방안을 제시하세요.
Optimist의 주장에서 과대평가된 부분을 지적하세요.
"""
    resp = run_agent(client, "Risk Analyst (리스크 분석가)",
                     "리스크를 체계적으로 분석하고 완화 전략을 제시하는 전문가",
                     risk_task, memory)
    results["risk"] = resp
    print_agent_speech("Risk Analyst (리스크 분석가)", resp)

    # Agent 6: Strategist — 최적 전략 합성
    strat_task = f"""
Optimist와 Risk Analyst의 토론을 종합하여:
주제 '{topic}'에 대한 최적의 실행 전략을 설계하세요.
- 단기(3개월) 우선 실행 사항
- 중기(1년) 목표
- 성공의 핵심 지표(KPI)
청중을 설득할 강력한 결론 문장으로 마무리하세요.
"""
    resp = run_agent(client, "Strategist (전략 합성가)",
                     "기회와 리스크를 통합하여 실행 가능한 전략을 설계하는 컨설턴트",
                     strat_task, memory, max_tokens=700)
    results["strategist"] = resp
    print_agent_speech("Strategist (전략 합성가)", resp)

    return results


def phase3_pdf_debate(client, frame: dict, research_data: dict, rounds: int,
                      pdf_texts: str) -> tuple[DebateMemory, list]:
    """선택된 도메인의 문제 → AI 솔루션 → 사업 설계 토론"""
    banner(3, f"The AI [X] 사업 설계 토론 ({rounds}라운드)")

    memory = DebateMemory()
    selected = frame.get("selected_domain", {})
    domain = selected.get("domain", "")
    pain_point = selected.get("pain_point", "")
    market_size = selected.get("market_size", "")
    why_fit = selected.get("why_fit", "")

    research_summary = "\n".join([
        f"Q: {v['question']}\nA: {v['answer'][:250]}"
        for k, v in research_data.items()
        if isinstance(v, dict) and "question" in v
    ])[:1500]

    # 에이전트들이 공유하는 컨텍스트
    # 논문은 "혁신 AI가 이런 것이다"는 참조 사례일 뿐, 우리 기술이 아님
    context = f"""
[우리가 해결할 도메인]
{domain}

[이 도메인의 핵심 문제]
{pain_point}

[시장 규모]
{market_size}

[AI 적합성 근거]
{why_fit}

[시장 조사 결과]
{research_summary}

[혁신 AI 가능성 참조 — 이런 수준의 AI가 존재한다는 맥락]
{pdf_texts[:800]}
""".strip()

    all_results = []

    # ── 라운드 1: 문제 정의 & AI 솔루션 설계 ──
    print(f"\n  {BOLD}── 라운드 1: 문제 정의 & AI 솔루션 설계 ──{RST}")

    resp = run_agent(client, "Problem Expert (문제 전문가)",
        f"'{domain}' 분야의 현장 전문가. 실제 사용자가 겪는 문제를 가장 잘 아는 사람",
        f"'{domain}' 도메인에서 사람들이 실제로 겪는 가장 큰 문제 3~4가지를 구체적으로 설명하세요.\n"
        f"문제의 심각성을 수치나 사례로 증명하고, 기존 해결책이 왜 부족한지 설명하세요.\n"
        f"컨텍스트:\n{context}",
        memory, max_tokens=600)
    print_agent_speech("Problem Expert (문제 전문가)", resp)

    resp = run_agent(client, "AI Solution Designer (AI 솔루션 설계자)",
        "최신 AI 기술로 실제 사업 솔루션을 설계하는 전문가",
        f"Problem Expert가 정의한 '{domain}' 문제들을 AI로 어떻게 해결할 수 있는지 설계하세요.\n"
        f"혁신 AI(멀티에이전트, 자율 추론, 실시간 분석 등)를 활용한 구체적 솔루션을 제안하세요.\n"
        f"이 솔루션의 이름은 'The AI [적절한 단어]' 형식으로 제안하고, 핵심 기능 3가지를 정의하세요.",
        memory, max_tokens=600)
    print_agent_speech("AI Solution Designer (AI 솔루션 설계자)", resp)

    resp = run_agent(client, "Innovative AI Agent (혁신 AI 아이디어러)",
        "아무도 시도하지 않은 방식으로 AI를 적용하는 급진적 혁신가. "
        "멀티에이전트 오케스트레이션, 피드백 루프, 자율 추론, 실시간 멀티모달 처리 등 "
        "최첨단 AI 기술을 조합해 '이게 진짜 가능해?' 싶은 아이디어를 낸다.",
        f"AI Solution Designer의 솔루션은 너무 평범하다. "
        f"'{domain}' 도메인에서 아무도 생각하지 못한 방식으로 AI를 적용하는 아이디어를 제안하라.\n\n"
        f"조건:\n"
        f"- 기존 업계 상식을 완전히 뒤집는 접근\n"
        f"- 멀티에이전트, 피드백 루프, 자율 학습, 예측 등 최신 AI 기술 조합 활용\n"
        f"- 'The AI [X]'가 단순 도구가 아닌 자율적 전문가처럼 동작하는 방식\n"
        f"- 구체적인 기술 메커니즘 포함 (어떻게 동작하는지)\n"
        f"기존 솔루션 디자이너 아이디어와 차별화되는 대담한 아이디어 2~3개를 제안하라.",
        memory, max_tokens=700)
    print_agent_speech("Innovative AI Agent (혁신 AI 아이디어러)", resp)

    resp = run_agent(client, "Devil's Advocate (비판적 검토자)",
        "솔루션의 약점을 날카롭게 찾아내는 비판적 사고자",
        f"AI Solution Designer와 Innovative AI Agent의 아이디어를 모두 검토하세요.\n"
        f"각각의 치명적 약점을 지적하되, 두 아이디어를 결합하면 더 강해지는 부분도 제안하세요.\n"
        f"기술 구현 난이도, 기존 경쟁자, 규제 리스크, 사용자 수용성 관점에서 분석하세요.",
        memory, max_tokens=600)
    print_agent_speech("Devil's Advocate (비판적 검토자)", resp)

    all_results.append({"round": 1, "focus": "문제 정의 & AI 솔루션"})

    # ── 라운드 2: 사업 모델 & 시장 검증 ──
    if rounds >= 2:
        print(f"\n  {BOLD}── 라운드 2: 사업 모델 & 시장 검증 ──{RST}")

        resp = run_agent(client, "Business Architect (사업 설계자)",
            "AI 솔루션을 수익성 있는 사업으로 설계하는 전략가",
            f"토론을 바탕으로 'The AI [{domain}]' 사업 모델을 설계하세요:\n"
            f"1. 타겟 고객 정의 (누가 돈을 내는가?)\n"
            f"2. 수익 모델 (구독/거래수수료/B2B 등) + 수치 추정\n"
            f"3. MVP — 6개월 내 만들 수 있는 핵심 기능 3가지\n"
            f"4. 초기 go-to-market 전략",
            memory, max_tokens=700)
        print_agent_speech("Business Architect (사업 설계자)", resp)

        resp = run_agent(client, "Market Validator (시장 검증가)",
            "VC 투자자 관점에서 시장 타당성을 검증하는 분석가",
            f"이 사업의 투자 매력도를 평가하세요:\n"
            f"1. TAM/SAM/SOM 추정\n"
            f"2. 직접 경쟁자 vs 기존 대안 분석\n"
            f"3. AI 차별점이 만드는 해자(moat)는?\n"
            f"4. 시리즈 A까지의 핵심 마일스톤",
            memory, max_tokens=600)
        print_agent_speech("Market Validator (시장 검증가)", resp)

        resp = run_agent(client, "Strategist (전략 합성가)",
            "모든 논의를 통합하여 최종 사업 방향을 확정하는 컨설턴트",
            f"지금까지 토론을 종합하여 'The AI [X]' 사업 소개서의 핵심 메시지를 확정하세요:\n"
            f"1. 최종 서비스명 (The AI [단어])\n"
            f"2. 한 줄 가치 제안 (tagline)\n"
            f"3. AI가 만드는 진짜 차별점 (기존 서비스와 다른 이유)\n"
            f"4. 투자자에게 전달할 핵심 메시지 한 문장",
            memory, max_tokens=700)
        print_agent_speech("Strategist (전략 합성가)", resp)
        all_results.append({"round": 2, "focus": "사업 모델 설계"})

    # ── 라운드 3+: 심화 검토 ──
    for round_num in range(3, rounds + 1):
        print(f"\n  {BOLD}── 라운드 {round_num}: 심화 검토 ──{RST}")

        resp = run_agent(client, "Domain Expert (도메인 현장 전문가)",
            f"'{domain}' 분야에서 20년 경력의 현장 전문가",
            f"이 AI 솔루션을 실제 '{domain}' 현장에 도입할 때:\n"
            f"- 현장에서 가장 먼저 요구할 기능은?\n"
            f"- 도입 시 가장 큰 저항/장벽은?\n"
            f"- 성공 사례가 되려면 무엇이 반드시 필요한가?",
            memory, max_tokens=600)
        print_agent_speech("Domain Expert (도메인 현장 전문가)", resp)

        resp = run_agent(client, "Investor (VC 투자자)",
            "AI 스타트업 전문 VC. 이 분야 10개 이상 포트폴리오 보유",
            f"투자자로서 이 사업에 대해:\n"
            f"- 투자 결정 요인 vs 거부 요인\n"
            f"- 가장 유사한 글로벌 성공 사례 (analogous company)\n"
            f"- 한국 시장에서의 특수한 기회/위험",
            memory, max_tokens=600)
        print_agent_speech("Investor (VC 투자자)", resp)

        all_results.append({"round": round_num, "focus": "심화 검토"})

    # ── 최종 합의 ──
    print(f"\n  {BOLD}── 최종 합의 ──{RST}")
    conclusion = run_agent(client, "Moderator (종합 분석가)",
        "전체 토론을 종합하여 사업 소개서의 핵심 내용을 확정하는 역할",
        f"전체 토론 결과를 바탕으로 사업 소개서 핵심 내용을 확정하세요:\n"
        f"1. 서비스명: The AI [X]\n"
        f"2. 해결하는 문제 (한 줄)\n"
        f"3. AI 솔루션의 핵심 차별점\n"
        f"4. 타겟 고객 및 수익 모델\n"
        f"5. 투자자에게 전달할 핵심 메시지",
        memory, max_tokens=800)
    print_agent_speech("Moderator (종합 분석가)", conclusion)
    memory.add_conclusion(conclusion)

    return memory, all_results


def phase4_pdf_synthesize(client, frame: dict, memory: DebateMemory) -> dict:
    """PDF 모드 전용 Phase 4 — 신사업 컨셉 → 사업 소개서 구조 설계"""
    banner(4, "The AI [X] 사업 소개서 설계")

    domains = frame.get("candidate_domains", [])
    ai_techs = frame.get("ai_technologies", [])
    tech_summary = "\n".join(f"- {t['name']}: {t['capability']}" for t in ai_techs)
    selected = frame.get("selected_domain", domains[0] if domains else {})
    domain_name = selected.get("domain", "")

    system = textwrap.dedent("""
        당신은 세계 최고의 스타트업 피치덱 디자이너입니다.
        "The AI Vet" 스타일의 사업 소개서를 JSON으로 설계하세요.
        청중은 투자자 또는 경영진입니다.

        ⚠️ 핵심 규칙:
        - title은 반드시 "The AI [도메인명]" 형식 (예: "The AI Vet", "The AI Lawyer", "The AI Farmer")
        - subtitle은 "새로운 형태의 [대상]을 위한 AI [역할]" 형식
        - InnovativeAI 섹션(기술 아키텍처)은 반드시 포함
        - 슬라이드는 아래 순서를 따를 것

        슬라이드 순서 (12장):
        1. 타이틀 (type: title) — "The AI [X]" + tagline
        2. 문제 데이터 (type: problem_data) — 시장 수치로 문제 크기 증명
        3. 구조적 문제 (type: problem_structure) — 3~4가지 구조적 문제표
        4. 기존 대안 현황 (type: competitive) — 기존 서비스들의 한계/병목
        5. 차별점 (type: differentiation) — AI 솔루션만의 차별점 2~3가지
        6. 시장 조사 (type: market) — TAM/SAM/SOM 또는 핵심 시장 데이터
        7. 고객 정의 (type: customer) — 타겟 고객 세그먼트
        8. 비즈니스 모델 (type: business) — 수익 구조 + 수치 추정
        9. MVP (type: mvp) — 핵심 기능 3가지
        10. InnovativeAI 아키텍처 (type: tech_arch) — AI 기술 구조 설명
        11. InnovativeAI 평가 기준 (type: tech_rubric) — AI 품질/안전성 기준
        12. 비전 (type: vision) — 최종 가치 제안

        반환 형식 (JSON만, 코드블록 없이):
        {
          "title": "The AI [X]",
          "subtitle": "한 줄 가치 제안",
          "tagline": "투자자를 설득할 핵심 문장",
          "slides": [
            {
              "title": "슬라이드 제목",
              "type": "title|problem_data|problem_structure|competitive|differentiation|market|customer|business|mvp|tech_arch|tech_rubric|vision",
              "key_points": ["포인트 1", "포인트 2", "포인트 3"],
              "highlight": "가장 강조할 한 문장",
              "data_points": ["수치 또는 근거 1", "수치 또는 근거 2"]
            }
          ],
          "closing_message": "마지막 슬라이드 메시지"
        }
        반드시 JSON만 반환하세요.
    """).strip()

    debate_summary = memory.last_n(8)
    conclusions = memory.all_conclusions()

    user_msg = textwrap.dedent(f"""
        보유 AI 기술:
        {tech_summary}

        AI 에이전트 토론 결과:
        {debate_summary[:2500]}

        최종 합의:
        {conclusions[:1000]}
    """).strip()

    info("Claude가 신사업 피치덱 구조 설계 중...")
    raw = claude_call(client, system, [{"role": "user", "content": user_msg}], max_tokens=3000)

    design = safe_json(raw)

    ok(f"사업명: {design.get('title', '')}")
    ok(f"가치 제안: {design.get('tagline', '')}")
    ok(f"슬라이드 {len(design.get('slides', []))}장 설계 완료")
    return design


def _round_freeform(client, memory, topic, round_num, debate_topics):
    """추가 라운드: 특정 토론 주제 심화"""
    results = {}
    dt = debate_topics[min(round_num - 1, len(debate_topics) - 1)]

    agents = [
        ("Domain Expert (도메인 전문가)",
         f"'{topic}' 분야의 최고 전문가. 기술적 깊이와 현장 경험 기반 주장",
         f"토론 주제 '{dt['topic']}'에 대해 도메인 전문가로서 심층 분석을 제공하세요. 관점: {dt['angle']}"),
        ("Audience Advocate (청중 대변인)",
         "발표를 듣는 청중의 관점에서 말하는 대변인. 이해하기 어려운 부분, 더 보고 싶은 내용 요청",
         f"청중 입장에서 '{dt['topic']}'에 대해 어떤 정보가 더 필요한지, 어떻게 설명해야 설득력 있는지 제시하세요"),
        ("Synthesizer (종합가)",
         "전문가와 청중 의견을 통합하여 최적 방향 제시",
         f"도메인 전문가와 청중 대변인의 의견을 통합하여 '{dt['topic']}'에 대한 최적의 발표 방향을 제시하세요"),
    ]

    for agent_name, role, task in agents:
        resp = run_agent(client, agent_name, role, task, memory)
        key = agent_name.split()[0].lower()
        results[key] = resp
        print_agent_speech(agent_name, resp)

    return results


# ═══════════════════════════════════════════════════════════════════
# Phase 4: Synthesis — 토론 결과로 슬라이드 구조 설계
# ═══════════════════════════════════════════════════════════════════
def phase4_synthesize(client, topic: str, frame: dict,
                      memory: DebateMemory) -> dict:
    banner(4, "Synthesis — 발표 구조 설계")

    system = textwrap.dedent("""
        당신은 세계 최고의 프레젠테이션 디자이너입니다.
        AI 에이전트들의 토론 결과와 리서치를 바탕으로
        최적의 발표 구조를 JSON으로 설계하세요.

        반환 형식 (JSON만 반환, 코드블록 없이):
        {
          "title": "발표 제목",
          "subtitle": "부제목",
          "tagline": "핵심 메시지 한 줄",
          "slides": [
            {
              "title": "슬라이드 제목",
              "type": "title|problem|research|solution|debate|strategy|technical|business|vision",
              "key_points": ["핵심 포인트 1", "핵심 포인트 2", "핵심 포인트 3"],
              "highlight": "가장 강조할 한 문장",
              "data_points": ["수치나 통계 1", "수치나 통계 2"]
            }
          ],
          "closing_message": "발표 마무리 메시지"
        }
        슬라이드는 6~9장 사이. 흐름: 도입 → 문제 → 리서치 → 해결책 → 토론 인사이트 → 전략 → 비전.
    """).strip()

    debate_summary = memory.last_n(8)
    conclusions = memory.all_conclusions()

    user_msg = textwrap.dedent(f"""
        발표 주제: {topic}
        한국어 제목: {frame.get('korean_title', topic)}
        청중: {frame.get('target_audience', '일반 비즈니스 청중')}

        AI 에이전트 토론 요약:
        {debate_summary[:2000]}

        합의된 결론:
        {conclusions[:800]}

        원래 예상 섹션: {', '.join(frame.get('slide_sections', []))}
    """).strip()

    info("Claude Synthesis Agent가 슬라이드 구조 설계 중...")
    raw = claude_call(client, system, [{"role": "user", "content": user_msg}], max_tokens=3000)

    design = safe_json(raw)

    ok(f"슬라이드 {len(design.get('slides', []))}장 설계 완료")
    ok(f"핵심 메시지: {design.get('tagline', '')}")

    return design


AGENT_HTML_STYLES = {
    "Researcher":  ("#16a34a", "#f0fdf4", "🔬"),
    "Devil":       ("#dc2626", "#fef2f2", "😈"),
    "Optimist":    ("#0891b2", "#ecfeff", "🚀"),
    "Risk":        ("#d97706", "#fffbeb", "⚠️"),
    "Strategist":  ("#2563eb", "#eff6ff", "🎯"),
    "Domain":      ("#7c3aed", "#f5f3ff", "🏛️"),
    "Audience":    ("#0891b2", "#ecfeff", "👥"),
    "Synthesizer": ("#2563eb", "#eff6ff", "🔗"),
    "Moderator":   ("#374151", "#f9fafb", "⚖️"),
}

def get_html_style(agent_name):
    for key, style in AGENT_HTML_STYLES.items():
        if key in agent_name:
            return style
    return ("#374151", "#f9fafb", "🤖")

def generate_debate_html(memory: DebateMemory, topic: str,
                         frame: dict, design: dict, out_dir: Path) -> Path:
    """토론 전체 내용을 보기 좋은 HTML로 생성"""

    # 발언을 라운드별로 분류
    round_labels = {
        "Researcher (리서치 분석가)":   "Round 1 — 리서치 검토",
        "Devil's Advocate (비판적 검토자)": "Round 1 — 리서치 검토",
        "Researcher (개선된 분석)":     "Round 1 — 리서치 검토",
        "Optimist (기회 분석가)":       "Round 2 — 전략 토론",
        "Risk Analyst (리스크 분석가)": "Round 2 — 전략 토론",
        "Strategist (전략 합성가)":     "Round 2 — 전략 토론",
        "Moderator (종합 분석가)":      "최종 합의",
    }

    def make_bubble(turn):
        agent = turn["agent"]
        content = turn["content"]
        color, bg, emoji = get_html_style(agent)
        # 줄바꿈을 <br>로
        content_html = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        label = round_labels.get(agent, "Round N — 심화 토론")
        return f"""
        <div class="bubble" style="border-left: 4px solid {color}; background: {bg};">
          <div class="agent-header" style="color: {color};">
            <span class="emoji">{emoji}</span>
            <strong>{agent}</strong>
            <span class="round-label">{label}</span>
          </div>
          <div class="content">{content_html}</div>
        </div>"""

    bubbles_html = "\n".join(make_bubble(t) for t in memory.turns)

    # 슬라이드 설계 요약
    slides_html = ""
    for i, s in enumerate(design.get("slides", []), 1):
        pts = "".join(f"<li>{p}</li>" for p in s.get("key_points", []))
        slides_html += f"""
        <div class="slide-card">
          <div class="slide-num">Slide {i}</div>
          <div class="slide-title">{s.get('title','')}</div>
          <ul class="slide-points">{pts}</ul>
          {"<div class='highlight'>💡 " + s.get('highlight','') + "</div>" if s.get('highlight') else ""}
        </div>"""

    core_qs = "".join(f"<li>{q}</li>" for q in frame.get("core_questions", []))
    conclusions_html = "".join(
        f"<p class='conclusion'>{c.replace(chr(10), '<br>')}</p>"
        for c in memory.conclusions
    )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Agent 토론 — {topic}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f172a; color: #e2e8f0; line-height: 1.7;
  }}
  .hero {{
    background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
    padding: 60px 40px; text-align: center;
    border-bottom: 2px solid #1e40af;
  }}
  .hero h1 {{ font-size: 2.5rem; color: #fff; margin-bottom: 12px; }}
  .hero .topic {{ font-size: 1.1rem; color: #93c5fd; }}
  .hero .meta {{ font-size: 0.85rem; color: #64748b; margin-top: 8px; }}

  .container {{ max-width: 900px; margin: 0 auto; padding: 40px 24px; }}

  /* 탭 */
  .tabs {{ display: flex; gap: 8px; margin-bottom: 32px; flex-wrap: wrap; }}
  .tab {{
    padding: 10px 22px; border-radius: 9999px; cursor: pointer;
    background: #1e293b; color: #94a3b8; border: 1px solid #334155;
    font-size: 0.9rem; transition: all 0.2s;
  }}
  .tab.active, .tab:hover {{
    background: #1e40af; color: #fff; border-color: #1e40af;
  }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  /* 버블 */
  .bubble {{
    border-radius: 12px; padding: 20px 24px;
    margin-bottom: 20px; border-left-width: 4px; border-left-style: solid;
  }}
  .agent-header {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 12px; flex-wrap: wrap;
  }}
  .emoji {{ font-size: 1.4rem; }}
  .agent-header strong {{ font-size: 1.05rem; }}
  .round-label {{
    margin-left: auto; font-size: 0.75rem;
    background: rgba(0,0,0,0.08); padding: 2px 10px;
    border-radius: 9999px; color: #64748b;
  }}
  .content {{ font-size: 0.97rem; color: #1e293b; white-space: pre-wrap; }}

  /* 슬라이드 카드 */
  .slides-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 16px;
  }}
  .slide-card {{
    background: #1e293b; border-radius: 12px; padding: 20px;
    border: 1px solid #334155;
  }}
  .slide-num {{ font-size: 0.75rem; color: #60a5fa; margin-bottom: 4px; }}
  .slide-title {{ font-size: 1rem; font-weight: 700; color: #f1f5f9; margin-bottom: 10px; }}
  .slide-points {{ padding-left: 18px; font-size: 0.88rem; color: #94a3b8; }}
  .slide-points li {{ margin-bottom: 4px; }}
  .highlight {{
    margin-top: 10px; padding: 8px 12px;
    background: #1e3a5f; border-radius: 8px;
    font-size: 0.85rem; color: #93c5fd; font-style: italic;
  }}

  /* 요약 */
  .summary-box {{
    background: #1e293b; border-radius: 12px; padding: 24px;
    border: 1px solid #334155; margin-bottom: 20px;
  }}
  .summary-box h3 {{ color: #93c5fd; margin-bottom: 14px; }}
  .summary-box ul {{ padding-left: 20px; color: #cbd5e1; }}
  .summary-box li {{ margin-bottom: 6px; }}
  .conclusion {{
    background: #0f2942; border-left: 3px solid #60a5fa;
    padding: 16px 20px; border-radius: 0 8px 8px 0;
    color: #e2e8f0; margin-bottom: 12px; font-size: 0.95rem;
  }}

  /* 통계 */
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 32px; }}
  .stat {{
    background: #1e293b; border-radius: 10px; padding: 16px 24px;
    border: 1px solid #334155; text-align: center; flex: 1; min-width: 120px;
  }}
  .stat-num {{ font-size: 2rem; font-weight: 700; color: #60a5fa; }}
  .stat-label {{ font-size: 0.8rem; color: #64748b; margin-top: 4px; }}
</style>
</head>
<body>
<div class="hero">
  <h1>🤖 AI Agent 토론</h1>
  <div class="topic">{topic}</div>
  <div class="meta">생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  총 발언: {len(memory.turns)}개</div>
</div>

<div class="container">

  <!-- 통계 -->
  <div class="stats">
    <div class="stat">
      <div class="stat-num">{len(memory.turns)}</div>
      <div class="stat-label">총 발언 수</div>
    </div>
    <div class="stat">
      <div class="stat-num">{len(set(t['agent'] for t in memory.turns))}</div>
      <div class="stat-label">참여 에이전트</div>
    </div>
    <div class="stat">
      <div class="stat-num">{len(design.get('slides', []))}</div>
      <div class="stat-label">설계된 슬라이드</div>
    </div>
    <div class="stat">
      <div class="stat-num">{sum(len(t['content']) for t in memory.turns):,}</div>
      <div class="stat-label">총 글자 수</div>
    </div>
  </div>

  <!-- 탭 -->
  <div class="tabs">
    <div class="tab active" onclick="showTab('debate')">💬 토론 전체</div>
    <div class="tab" onclick="showTab('slides')">📊 슬라이드 설계</div>
    <div class="tab" onclick="showTab('summary')">📋 요약 & 결론</div>
  </div>

  <!-- 토론 탭 -->
  <div id="tab-debate" class="tab-content active">
    {bubbles_html}
  </div>

  <!-- 슬라이드 탭 -->
  <div id="tab-slides" class="tab-content">
    <div style="margin-bottom:20px;">
      <h2 style="color:#f1f5f9;">{design.get('title', topic)}</h2>
      <p style="color:#93c5fd; font-style:italic; margin-top:6px;">{design.get('tagline','')}</p>
    </div>
    <div class="slides-grid">{slides_html}</div>
  </div>

  <!-- 요약 탭 -->
  <div id="tab-summary" class="tab-content">
    <div class="summary-box">
      <h3>🎯 핵심 연구 질문</h3>
      <ul>{core_qs}</ul>
    </div>
    <div class="summary-box">
      <h3>⚖️ Moderator 최종 결론</h3>
      {conclusions_html if conclusions_html else '<p style="color:#64748b;">결론 없음</p>'}
    </div>
    <div class="summary-box">
      <h3>📝 마무리 메시지</h3>
      <p class="conclusion">{design.get('closing_message','')}</p>
    </div>
  </div>

</div>

<script>
function showTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}}
</script>
</body>
</html>"""

    safe = re.sub(r'[^\w가-힣]', '_', topic)[:20]
    ts   = datetime.now().strftime("%m%d_%H%M")
    html_path = out_dir / f"{safe}_토론뷰어_{ts}.html"
    html_path.write_text(html, encoding="utf-8")
    ok(f"HTML 뷰어 저장: {BOLD}{html_path}{RST}")
    return html_path



# ═══════════════════════════════════════════════════════════════════
# Phase 5: NotebookLM 슬라이드 생성
# ═══════════════════════════════════════════════════════════════════
def phase5_nlm_slides(nb_id: str, design: dict, memory: DebateMemory,
                      topic: str, lang: str) -> bool:
    banner(5, "NotebookLM 슬라이드 생성")

    # ① 토론 결과 + 슬라이드 구조를 NLM 소스로 추가
    synthesis_text = f"""# {topic} — AI Agent 토론 결과 및 발표 구조

## 핵심 메시지
{design.get('tagline', '')}

## 발표 제목
{design.get('title', topic)} / {design.get('subtitle', '')}

## 슬라이드 구성 ({len(design.get('slides', []))}장)
"""
    for i, s in enumerate(design.get("slides", []), 1):
        synthesis_text += f"\n### 슬라이드 {i}: {s.get('title', '')}\n"
        for pt in s.get("key_points", []):
            synthesis_text += f"- {pt}\n"
        if s.get("speaker_note"):
            synthesis_text += f"(발표 노트: {s['speaker_note']})\n"

    synthesis_text += "\n## AI 에이전트 토론 핵심 결론\n"
    for turn in memory.turns[-5:]:
        excerpt = turn["content"][:300].replace("\n", " ")
        synthesis_text += f"\n**[{turn['agent']}]** {excerpt}…\n"

    info("토론 결과를 NLM 소스로 추가 중...")
    _, _, rc = run_nlm("source", "add", nb_id,
                       "--text", synthesis_text,
                       "--title", f"{topic} — 토론 결과 요약")
    if rc == 0:
        ok("소스 추가 완료")
    else:
        warn("소스 추가 실패 (계속 진행)")

    time.sleep(5)

    # ② 슬라이드 생성
    title = design.get('title', f'The AI {topic}')
    tagline = design.get('tagline', '')
    focus = (
        f"사업 소개서: {title}. "
        f"{tagline} "
        f"슬라이드 구성: 문제 → 기존 대안 한계 → AI 차별점 → 시장 조사 → 고객 정의 → 비즈니스 모델 → MVP → InnovativeAI 기술 아키텍처 → 비전. "
        f"슬라이드 제목과 주제는 '{title}'로 시작할 것."
    )
    info(f"NotebookLM 슬라이드 생성 중... (포커스: {focus[:80]})")

    _, err_out, rc = run_nlm(
        "slides", "create", nb_id,
        "--focus",    focus,
        "--language", lang,
        "--confirm",
    )

    if rc == 0:
        ok("NotebookLM 슬라이드 생성 완료!")
        ok(f"→ notebooklm.google.com 에서 '{topic}' 노트북을 열어 확인하세요")
        return True
    else:
        warn(f"NLM 슬라이드 생성 실패: {err_out[:200]}")
        warn("notebooklm.google.com 에서 직접 슬라이드를 생성하세요")
        return False


# ═══════════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════════
def main():
    args = parse_args()

    out_dir = BASE_DIR / args.out
    out_dir.mkdir(exist_ok=True)

    print(f"\n{BOLD}{'═'*65}{RST}")
    print(f"{BOLD}  AI 리서치 & 발표자료 자동 생성 파이프라인{RST}")
    print(f"{BOLD}{'═'*65}{RST}")
    # .env 로드
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit(f"{RED}[ERROR]{RST} ANTHROPIC_API_KEY 환경변수를 설정하세요.\n"
                 f"  export ANTHROPIC_API_KEY='sk-ant-...'")

    client = anthropic.Anthropic(api_key=api_key)

    # ── 모드 판단 ──
    innovative_mode = args.innovative_ai or bool(args.pdf)
    topic = args.topic or "AI 혁신기술 신사업"

    mode_label = "🚀 혁신 AI 신사업 자동 발굴" if innovative_mode else f"🔍 주제 리서치: {topic}"
    print(f"  모드    : {BOLD}{mode_label}{RST}")
    print(f"  라운드  : {args.rounds}  |  NLM 모드: {args.mode}  |  출력: {out_dir}")
    print(f"  시작    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ════════════════════════════════════════════════════════
    #  혁신 AI 신사업 발굴 모드
    # ════════════════════════════════════════════════════════
    if innovative_mode:
        # Phase 0 (PDF 옵션): PDF 텍스트 추출
        extra_knowledge = ""
        if args.pdf:
            extra_knowledge = phase0_extract_pdfs(args.pdf)

        # Phase 1: 아이디어 10개 생성
        if extra_knowledge:
            frame = phase1_pdf_mode(client, extra_knowledge)
        else:
            frame = phase1_innovative_ai(client)

        if not frame.get("candidate_domains"):
            sys.exit(f"{RED}[ERROR]{RST} 아이디어 생성 실패")

        # Phase 2: 10개 아이디어 토론 → 최고 아이디어 선정
        frame = phase2_idea_debate(client, frame)

        selected = frame.get("selected_domain", frame["candidate_domains"][0])
        topic = selected.get("service_name", selected.get("domain", ""))
        selected["domain"] = selected.get("domain", topic)

        # Phase 3: NLM 시장 조사 (선정된 아이디어)
        nb_id, research_data = ("", {})
        if not args.no_nlm:
            nb_id, research_data = phase2_nlm(topic, frame, args.mode, args.lang)
        else:
            warn("--no-nlm: NLM 건너뜀")

        # Phase 4: 리서치 기반 심화 토론
        memory, round_results = phase3_pdf_debate(
            client, frame, research_data, args.rounds,
            extra_knowledge or INNOVATIVE_AI_KNOWLEDGE
        )

        # Phase 5: 사업 소개서 설계
        design = phase4_pdf_synthesize(client, frame, memory)
        topic  = design.get("title", f"The AI {topic}")

    # ════════════════════════════════════════════════════════
    #  일반 주제 리서치 모드
    # ════════════════════════════════════════════════════════
    else:
        if not args.topic:
            sys.exit(f"{RED}[ERROR]{RST} 주제를 입력하세요.")

        # Phase 1: 주제 분석
        frame = phase1_analyze(client, topic)

        # Phase 2: NLM 웹 검색
        nb_id, research_data = ("", {})
        if not args.no_nlm:
            nb_id, research_data = phase2_nlm(topic, frame, args.mode, args.lang)
        else:
            warn("--no-nlm 플래그: NLM 건너뜀")

        # Phase 3: Multi-Agent 토론
        memory, round_results = phase3_debate(
            client, topic, frame, research_data, args.rounds
        )

        # Phase 4: 발표 구조 합성
        design = phase4_synthesize(client, topic, frame, memory)

    # ── Phase 5: NotebookLM 슬라이드 생성 ──
    ts   = datetime.now().strftime("%m%d_%H%M")
    safe = re.sub(r'[^\w가-힣]', '_', topic)[:20]

    nlm_slides_ok = False
    if nb_id:
        nlm_slides_ok = phase5_nlm_slides(nb_id, design, memory, topic, args.lang)
    else:
        warn("NLM 노트북 없음 — 슬라이드 생성 건너뜀 (--no-nlm 모드)")

    # ── 결과물 저장 (텍스트 파일만) ──
    (out_dir / f"{safe}_framework_{ts}.json").write_text(
        json.dumps(frame, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / f"{safe}_design_{ts}.json").write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    debate_txt = "\n\n".join(
        f"[{t['agent']}]\n{t['content']}" for t in memory.turns
    )
    (out_dir / f"{safe}_debate_{ts}.txt").write_text(debate_txt, encoding="utf-8")

    if research_data:
        research_txt = "\n\n".join(
            f"Q: {v['question']}\nA: {v['answer']}"
            for k, v in research_data.items()
            if isinstance(v, dict) and "question" in v
        )
        (out_dir / f"{safe}_research_{ts}.txt").write_text(research_txt, encoding="utf-8")

    # ── HTML 토론 뷰어 생성 ──
    html_path = generate_debate_html(memory, topic, frame, design, out_dir)

    # ── 최종 요약 ──
    print(f"\n{BOLD}{GREEN}{'═'*65}{RST}")
    print(f"{BOLD}{GREEN}  완료! 생성된 결과물:{RST}")
    print(f"{BOLD}{GREEN}{'═'*65}{RST}")
    if nlm_slides_ok:
        print(f"  {GREEN}📑{RST}  NotebookLM 슬라이드 : {BOLD}notebooklm.google.com{RST} 에서 확인")
    else:
        print(f"  {YELL}📑{RST}  NotebookLM 슬라이드 : NLM 노트북이 있어야 생성됩니다")
    print(f"  {GREEN}🌐{RST}  토론 뷰어 (HTML)    : {BOLD}{html_path}{RST}")
    print(f"  {GREEN}💬{RST}  토론 텍스트         : {out_dir}/{safe}_debate_{ts}.txt")
    print(f"  {GREEN}📋{RST}  슬라이드 설계       : {out_dir}/{safe}_design_{ts}.json")
    if nb_id:
        print(f"  {GREEN}📚{RST}  NLM 노트북 ID      : {DIM}{nb_id}{RST}")
    print(f"\n  종료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n  {BLUE}👉 토론 내용 보기:{RST} open \"{html_path}\"\n")

    # HTML 자동 오픈
    subprocess.run(["open", str(html_path)])

    # NLM 슬라이드 생성 완료 시 notebooklm.google.com 자동 오픈
    if nlm_slides_ok:
        print(f"  {BLUE}📑 NotebookLM 열기...{RST}")
        subprocess.run(["open", "https://notebooklm.google.com"])


if __name__ == "__main__":
    main()
