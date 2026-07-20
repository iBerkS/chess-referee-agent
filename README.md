# Chess Referee Agent

An LLM agent that defers chess rule-checking to a real engine instead of trusting the model's own (often hallucinated) understanding of legal moves.

This project builds on [`chess-finetune-qwen`](https://github.com/iBerkS/chess-finetune-qwen), where a LoRA fine-tuned Qwen 2.5 7B was found to reason inconsistently about concrete chess positions despite otherwise strong performance on rules and openings. Rather than trying to fix that through more fine-tuning, this project pairs the model with [`python-chess`](https://python-chess.readthedocs.io/) via tool calling — the model decides *what* to check, a real rules engine decides *whether it's actually legal*.

## Why this matters

LLMs are good at describing chess concepts in language but unreliable at tracking concrete board state — a limitation that shows up as confidently wrong answers rather than "I don't know" answers. Tool calling lets the model stay in its lane (language, decision-making about *what* to check) while offloading the part it's bad at (exact board state and move legality) to deterministic code.

## Setup

```bash
pip install -r requirements.txt
```

Requires [LM Studio](https://lmstudio.ai/) running locally with the fine-tuned model loaded, serving an OpenAI-compatible API at `http://localhost:1234`.

## Project structure

```
chess-referee-agent/
├── docs/           # Phase-by-phase findings and architectural decisions
├── src/            # Working agent implementation
├── tests/          # Sanity checks and exploratory scripts
├── requirements.txt
```

## Roadmap

- [x] **Phase 1 — Single tool call.** Verified the full round-trip: model receives a request, generates a tool call, the tool call is executed against a real `python-chess` board, and the result is fed back for a final response.
  - **Key finding:** the model hallucinates a FEN board position even when one is explicitly provided in the system prompt with an instruction never to guess. See [`docs/PHASE1.md`](docs/PHASE1.md) for the full writeup.
  - **Architectural decision:** the model will never receive or generate FEN. Board state is held server-side; the model only ever proposes a move in UCI notation.
- [x] **Phase 2 — Agent loop.** The model reacts to a tool result and makes a follow-up decision — e.g., suggesting a correction on an illegal move, ~~or requesting a position evaluation via Stockfish~~ on a legal one.
- [ ] **Phase 3 — Multiple tools + memory.** Combine move validation, position evaluation, and opening recognition into one agent, with conversation history retained across turns.

## Related

- [`chess-finetune-qwen`](https://github.com/iBerkS/chess-finetune-qwen) — the fine-tuned model this project is built on, including the cross-lingual and reasoning limitations that motivated this agent architecture.