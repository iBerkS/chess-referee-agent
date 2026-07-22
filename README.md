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

**Phase 3a onward** additionally requires the [Stockfish](https://stockfishchess.org/download/) engine binary. This is *not* installed via pip — download the binary for your platform and place it locally (e.g. `bin/stockfish.exe`); the agent connects to it via an explicit file path, so no system-wide install or PATH changes are needed.

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
  - **Key finding:** blind retry alone isn't enough — after an illegal move, the model's next guess was no more reliable than its first (e.g. proposing a move from a square with no piece on it). See [`docs/PHASE2.md`](docs/PHASE2.md).
  - **Fix:** tool results now include the actual legal moves for the piece in question when a move is illegal, turning the retry into a selection task rather than a generation task — verified to resolve the inconsistency.
- [x] **Phase 3a — Stockfish integration.** A third tool for position evaluation on legal moves, following the same helper+dispatch pattern as move validation. Requires a local Stockfish binary (see Setup).
  - **Key finding:** an ambiguous illegal-move reason (empty hint list) was indistinguishable from "no legal moves for this piece" vs. "it's not this piece's turn" — the model filled the gap with invented rules. See [`docs/PHASE3.md`](docs/PHASE3.md).
  - **Known limitation:** the model occasionally states an intention without calling the corresponding tool, or misdescribes a move's piece/square in its final response — likely a capacity limit of the 7B model rather than a fixable prompting issue.
- [x] **Phase 3b — Conversation memory.** `ask()` currently rebuilds message history from scratch on every call; board state persists but conversation context doesn't. Separated from 3a to avoid conflating two independent architectural changes.
  - **Verified:** the agent correctly recalls context several turns back (e.g. "what was the very first move of this game?") without re-deriving it from board state. See [`docs/PHASE3B.md`](docs/PHASE3B.md).## Related

## Evals

Alongside the phase-based development log, this project includes a small eval system (`tests/evals/`) to measure how *consistently* the model behaves across repeated runs, rather than relying on one-off manual testing. Unlike the deterministic unit-test mindset, evals here score the model statistically — each scenario is run N times (default 5) and scored as a pass rate per check, since the same prompt can produce different tool-call behavior across runs.

- **Findings so far:** intent-to-action follow-through (stating a move but not calling the tool) and move-description accuracy (misnaming the piece just moved) are the weakest measured behaviors (0-33% pass rate); rule-hallucination avoidance and turn efficiency are consistently strong (100%).
- See [`docs/EVALS.md`](docs/EVALS.md) for the full methodology, results table, and known limitations of the eval harness itself.

- [`chess-finetune-qwen`](https://github.com/iBerkS/chess-finetune-qwen) — the fine-tuned model this project is built on, including the cross-lingual and reasoning limitations that motivated this agent architecture.