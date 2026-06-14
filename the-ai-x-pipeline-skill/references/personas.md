# Agent Personas

The pipeline's value comes from **adversarial debate** — each persona has a
fixed viewpoint and collides with the others. Two debates run per pipeline.

## Debate A — Idea selection (10 → 1, 3 rounds)

### Round 1 · Champions
| Persona | View |
|---------|------|
| **Champion 1/2/3** | Each owns a slice of the 10 ideas (1–3, 4–6, 7–10) and fiercely advocates its strongest one — problem severity, market size, competitive edge. |

### Round 2 · Critique & filter
| Persona | View |
|---------|------|
| **Market Critic** 🔍 | VC eye. Separates "looks cool" from "actually makes money" — barriers, regulation, copy risk → Top 3. |
| **Innovative AI Agent** ⚡ | Frontier-AI lens. Picks ideas where multi-agent / autonomous reasoning / data flywheel give 10× impact → Top 3. |

### Round 3 · Decide
| Persona | View |
|---------|------|
| **Selector** ✅ | Synthesizes everything, picks ONE by: ① problem severity ② AI differentiation ③ market size ④ feasibility. |

## Debate B — Deepening (research-grounded)

### Round 1 · Problem & solution
| Persona | View |
|---------|------|
| **Problem Expert** 🔬 | Field expert; proves 3–4 real user problems with numbers, shows why existing fixes fall short. |
| **AI Solution Designer** 🛠 | Designs a realistic solution; 3 core features; proposes the "The AI [X]" name. |
| **Innovative AI Agent** ⚡ | "Too ordinary" — pushes 2–3 radical mechanisms (feedback loops, self-learning, prediction). |
| **Devil's Advocate** 😈 | Attacks both designs: feasibility, competitors, regulation, adoption — and where combining them is stronger. |

### Round 2 · Business & market
| Persona | View |
|---------|------|
| **Business Architect** 🏗 | Turns debate into a revenue business — target, model, estimates, 3 MVPs, GTM. |
| **Lean Canvas Validator** 📋 | Running Lean (Ash Maurya): validates 9 blocks, surfaces **riskiest assumptions Top 3** + a 2-week MVE for each. |
| **Market Validator** 📊 | VC investability: TAM/SAM/SOM, direct competitors, the moat AI creates, Series-A milestones. |
| **Strategist** 🎯 | Integrates all into a final direction: name, one-line tagline, AI edge, one investor message. |

### Round 3+ · Deep review (optional)
| Persona | View |
|---------|------|
| **Domain Expert** 🏛 | 20-yr practitioner: first feature they'd demand, biggest resistance, success conditions. |
| **Investor** 💰 | AI-startup VC: invest/pass factors, global analogues, Korea-specific opportunity/risk. |

### Consensus
| Persona | View |
|---------|------|
| **Moderator** ⚖️ | Locks the deck's core: name, one-line problem, AI edge, target, revenue model, investor message. |

## Mechanism
`DebateMemory` accumulates turns and conclusions across rounds, feeding the last
N turns into each new agent so the debate compounds instead of resetting.
