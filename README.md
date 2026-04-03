# The AI [X] Pipeline

> AI가 스스로 세상의 문제를 찾고, 토론하고, 사업 소개서를 만든다.

---

## 개요

**The AI [X] Pipeline**은 Claude AI와 Google NotebookLM을 연결해,  
아이디어 발굴부터 사업 소개서 슬라이드 생성까지 전 과정을 자동화하는 파이프라인입니다.

"The AI Vet", "The AI Lawyer", "The AI Farmer"처럼  
실생활의 문제를 혁신적인 AI로 해결하는 새로운 사업 아이디어를 자율적으로 도출합니다.

---

## 파이프라인 구조

```
Phase 1  →  아이디어 10개 자유 발굴
            실생활/전문직/산업 현장의 미해결 문제 탐색
            각 아이디어: 문제 정의 + AI 적합성 + 시장 규모

Phase 2  →  AI 에이전트 토론 — 최고 아이디어 선정
            Champion (×3): 담당 아이디어 옹호
            Market Critic: 시장성 냉정 평가
            Innovative AI Agent: AI 혁신 잠재력 평가
            Selector: 최종 1개 선정

Phase 3  →  Google NotebookLM 웹 리서치
            선정된 아이디어의 시장 데이터, 경쟁사, 트렌드 수집

Phase 4  →  리서치 기반 심화 토론
            Problem Expert: 문제 구조 분석
            AI Solution Designer: 현실적 솔루션 설계
            Innovative AI Agent: 대담한 AI 적용 아이디어
            Devil's Advocate: 비판 & 약점 분석
            Business Architect: 사업 모델 설계
            Market Validator: 시장 검증

Phase 5  →  The AI [X] 사업 소개서 설계
            12장 구성: 문제 → AI 솔루션 → 시장 → 비즈니스 모델 → MVP → 비전

Phase 6  →  Google NotebookLM 슬라이드 자동 생성
```

---

## 아웃풋 예시

파이프라인이 자율적으로 생성한 사업 소개서:

| 서비스명 | 도메인 | 핵심 문제 |
|---------|--------|----------|
| The AI Caregiver | 노인 돌봄 | 돌봄 인력 부족 & 고비용 |
| The AI Accountant | 세무/회계 | 중소기업 세무 접근성 |
| The AI Taxmate | 세금 신고 | 개인 세금 신고 복잡성 |

---

## 사용 방법

### 1. 설치

```bash
git clone https://github.com/leten02/the-ai-x-pipeline
cd the-ai-x-pipeline

python3 -m venv .venv
.venv/bin/pip install anthropic
```

### 2. 인증

**Anthropic API Key** 설정:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**NotebookLM 로그인** (Chrome 필요):
```bash
pip install notebooklm-cli
nlm login
```

### 3. 실행

```bash
# 대화형 실행 (추천)
.venv/bin/python3 run.py

# 직접 실행
.venv/bin/python3 pipeline.py --innovative-ai --rounds 2 --mode fast
```

### 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--rounds` | 토론 라운드 수 | 2 |
| `--mode` | NLM 검색 모드 (`fast` / `deep`) | `fast` |
| `--no-nlm` | NotebookLM 없이 Claude만 사용 | False |
| `--lang` | 슬라이드 언어 | `ko` |

---

## 기술 스택

| 구성요소 | 역할 |
|---------|------|
| **Claude (Anthropic)** | 아이디어 생성, 멀티 에이전트 토론, 사업 소개서 설계 |
| **Google NotebookLM** | 웹 리서치, 슬라이드 자동 생성 |
| **notebooklm-cli** | NotebookLM API 연동 |

---

## 에이전트 구성

### Phase 2 — 아이디어 선정 토론

| 에이전트 | 역할 |
|---------|------|
| Champion 1/2/3 | 담당 아이디어 옹호 |
| Market Critic | VC 관점 시장성 평가 |
| Innovative AI Agent | AI 혁신 잠재력 평가 |
| Selector | 최종 아이디어 선정 |

### Phase 4 — 심화 토론

| 에이전트 | 역할 |
|---------|------|
| Problem Expert | 도메인 문제 구조 분석 |
| AI Solution Designer | 현실적 AI 솔루션 설계 |
| Innovative AI Agent | 대담한 AI 적용 아이디어 제안 |
| Devil's Advocate | 약점 비판 & 결합 포인트 탐색 |
| Business Architect | 수익 모델 & MVP 설계 |
| Market Validator | TAM/SAM/SOM & 경쟁 분석 |
| Strategist | 최종 전략 합성 |

---

## 결과물

파이프라인 실행 시 `output/` 폴더에 생성:

- **NotebookLM 슬라이드** — `notebooklm.google.com`에서 확인
- **토론 뷰어** (HTML) — 전체 에이전트 토론 내용
- **사업 소개서 설계** (JSON) — 슬라이드 구조 데이터
- **리서치 결과** (TXT) — NotebookLM 조사 내용

---

## 주의사항

- NotebookLM은 Google 계정 로그인이 필요합니다
- `fast` 모드: 약 30초 소요 / `deep` 모드: 약 5분 소요
- Anthropic API 비용이 발생합니다 (라운드당 약 $0.05~0.15)

---

## 라이선스

MIT
