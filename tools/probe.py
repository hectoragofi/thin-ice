"""Stateless next-move probe: how far a model looks ahead when there is no session to manage.

Each Blue move is one fresh API call: the rules, one position, "play one move". No tools, no
conversation, nothing carried over between calls. Puzzles come from the held-out evaluation
pool and are played to the end by training.common.rollout, the same code and the same metric
as the Qwen curve, so the result compares directly with the fine-tuned model and with the
Harbor task score.

The solver's pack grades every call into one of four bins:
  right      the move keeps a forced win inside the puzzle's move allowance
  wrong      a legal move that gives the win away, or keeps it but too slowly
  illegal    the answer is not a legal move
  no_answer  the reply ended without a move (for example the output limit hit while thinking)

Calls are cached in results/probe/<model>[-tag].jsonl, so an interrupted run resumes where it
stopped and a finished run reprints its report for free. Use --tag for an independent repeat.

  python tools/probe.py --model gemini-4-argon --tiers 1-5 --per-tier 10
  python tools/probe.py --model oracle      (free self-test: the solver's own move, scores 1.0)
  python tools/probe.py --model random      (free: a random legal move, the chance level)
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import random
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thinice.board import RULES, key, move_name  # noqa: E402
from thinice.session import LOSS0, pick  # noqa: E402
from training.common import PACKS, eval_pool, rollout  # noqa: E402

API = "https://generativelanguage.googleapis.com/v1beta/models/"
OUT = ROOT / "results" / "probe"
HARNESS_OUTPUT_CAP = 64000  # the task image sets OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX to this
FAKE = ("oracle", "random")
MOVE = re.compile(r"\b([a-h][1-9])\s*-\s*([a-h][1-9])\b")
VERDICTS = ("right", "wrong", "illegal", "no_answer")

SYSTEM = (
    "You play Blue in Thin Ice. These are the complete rules.\n\n"
    f"{RULES}\n"
    "You are shown one position in which Blue has a forced win. Work the move out by thinking: "
    "there are no tools and no code. Reply with one move in from-to form, for example a1-a6, and nothing else."
)


class Fatal(RuntimeError):
    """Stops the run. Everything answered so far is in the cache, so the same command resumes."""


def api_key(var: str = "GEMINI_API_KEY") -> str:
    value = os.environ.get(var)
    env = ROOT / ".env"
    if not value and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, rest = line.partition("=")
            if name.strip() == var:
                value = rest.strip().strip("\"'")
    if not value:
        raise Fatal(f"{var} is not set and not in .env")
    return value


def http(url: str, body: dict | None = None, timeout: int = 600, headers: dict | None = None):  # per read: a silent stream is retried after 10 min
    data = json.dumps(body).encode() if body is not None else None
    headers = headers or {"x-goog-api-key": api_key()}
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


# Other providers. Same prompt, same one-move-per-fresh-call protocol, same row fields:
# "thoughts" is the thinking-token count the API reports, "out" the answer tokens without it.
ANTHROPIC = "https://api.anthropic.com/v1/"
NVIDIA = "https://integrate.api.nvidia.com/v1/"


def provider_of(model: str) -> str:
    return "anthropic" if model.startswith("claude-") else "nvidia" if "/" in model else "gemini"


def anthropic_headers() -> dict:
    return {"x-api-key": api_key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"}


def nvidia_headers() -> dict:
    return {"Authorization": f"Bearer {api_key('NVIDIA_API_KEY')}", "Accept": "text/event-stream"}


def output_limit(model: str, provider: str = "gemini") -> int:
    if provider == "anthropic":
        with http(ANTHROPIC + "models/" + model, timeout=60, headers=anthropic_headers()) as resp:
            return int(json.load(resp)["max_tokens"])
    if provider == "nvidia":
        return HARNESS_OUTPUT_CAP  # the OpenAI-style API does not publish an output limit; the harness cap applies
    with http(API + model, timeout=60) as resp:
        return int(json.load(resp)["outputTokenLimit"])


def sse(resp):
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            yield json.loads(line[5:])


def ask_other(provider: str, model: str, user: str, max_output: int) -> dict:
    """ask() for Anthropic's Messages API and NVIDIA's OpenAI-compatible API. Thinking is left at the API default."""
    if provider == "anthropic":
        # No temperature/top_p/top_k and no thinking block: the model's default (adaptive) thinking applies.
        url, headers = ANTHROPIC + "messages", anthropic_headers()
        body = {"model": model, "max_tokens": max_output, "system": SYSTEM, "stream": True,
                "messages": [{"role": "user", "content": user}]}
    else:
        url, headers = NVIDIA + "chat/completions", nvidia_headers()
        body = {"model": model, "max_tokens": max_output, "stream": True, "stream_options": {"include_usage": True},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    err = ""
    for wait in (0, 15, 45, 120, 300):
        time.sleep(wait)
        started, text, finish, usage = time.time(), "", None, {}
        try:
            with http(url, body, headers=headers) as resp:
                for chunk in sse(resp):
                    if provider == "anthropic":
                        kind = chunk.get("type")
                        if kind == "message_start":
                            usage = dict(chunk["message"].get("usage") or {})
                        elif kind == "content_block_delta" and chunk["delta"].get("type") == "text_delta":
                            text += chunk["delta"]["text"]  # thinking deltas are skipped: not part of the answer
                        elif kind == "message_delta":
                            finish = chunk["delta"].get("stop_reason") or finish
                            usage.update(chunk.get("usage") or {})
                        elif kind == "error":
                            raise OSError(f"stream error: {chunk.get('error')}")
                    else:
                        usage = chunk.get("usage") or usage
                        for ch in chunk.get("choices", []):
                            text += (ch.get("delta") or {}).get("content") or ""  # reasoning_content is skipped
                            finish = ch.get("finish_reason") or finish
            if finish is None:
                err = "the stream ended without a finish reason"
                continue
            if provider == "anthropic":
                prompt = sum(usage.get(f) or 0 for f in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                total = usage.get("output_tokens", 0)
                thoughts = (usage.get("output_tokens_details") or {}).get("thinking_tokens")
            else:
                prompt = usage.get("prompt_tokens", 0)
                total = usage.get("completion_tokens", 0)
                thoughts = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            row = {
                "text": text.strip()[-300:],
                "head": text.strip()[:300],  # for --parse first: models that explain after the move
                "finish": "MAX_TOKENS" if finish in ("max_tokens", "length") else finish,
                "prompt": prompt,
                "thoughts": thoughts or 0,
                "out": total - (thoughts or 0),
                "secs": round(time.time() - started, 1),
            }
            if thoughts is None:
                row["thinking_split"] = False  # the API gave only a total; "out" holds thinking plus answer
            return row
        except urllib.error.HTTPError as exc:
            err = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"
            if exc.code not in (429, 500, 502, 503, 504, 529):
                raise Fatal(f"{model}: {err}") from None
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
            err = repr(exc)
    raise Fatal(f"{model}: gave up after retries: {err}")


def ask(model: str, user: str, max_output: int, level: str | None) -> dict:
    """One fresh request. Returns the answer text (thoughts left out), why it ended and the token counts."""
    thinking = {"includeThoughts": True}  # thought summaries keep the stream alive; they are not part of the answer
    if level:
        thinking["thinkingLevel"] = level
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_output, "thinkingConfig": thinking},
    }
    err = ""
    for wait in (0, 15, 45, 120, 300):
        time.sleep(wait)
        started, text, finish, usage = time.time(), "", None, {}
        try:
            with http(f"{API}{model}:streamGenerateContent?alt=sse", body) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = json.loads(line[5:])
                    usage = chunk.get("usageMetadata") or usage
                    for cand in chunk.get("candidates", []):
                        finish = cand.get("finishReason") or finish
                        for part in (cand.get("content") or {}).get("parts", []):
                            if not part.get("thought"):
                                text += part.get("text", "")
            if finish is None:
                err = "the stream ended without a finish reason"
                continue
            return {
                "text": text.strip()[-300:],
                "finish": finish,
                "prompt": usage.get("promptTokenCount", 0),
                "thoughts": usage.get("thoughtsTokenCount", 0),
                "out": usage.get("candidatesTokenCount", 0),
                "secs": round(time.time() - started, 1),
            }
        except urllib.error.HTTPError as exc:
            err = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"
            if exc.code not in (429, 500, 502, 503, 504):
                raise Fatal(f"{model}: {err}") from None
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
            err = repr(exc)
    raise Fatal(f"{model}: gave up after retries: {err}")


class Probe:
    def __init__(self, args):
        self.args = args
        self.fake = args.model in FAKE
        self.provider = args.provider or provider_of(args.model)
        self.rng = random.Random(0)
        self.lock = threading.Lock()
        self.rows: list = []  # every call of this run, cached or new
        self.new = 0
        OUT.mkdir(parents=True, exist_ok=True)
        self.name = args.model.replace("/", "_") + (f"-{args.tag}" if args.tag else "")  # nvidia/x is a file name
        self.path = OUT / f"{self.name}.jsonl"
        self.cache = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.cache[row["k"]] = row
        self.max_output = 0 if self.fake else (args.max_output or min(output_limit(args.model, self.provider), HARNESS_OUTPUT_CAP))

    def answer(self, att, entries: list) -> dict:
        if self.fake:
            wins = [e for e in entries if e[2] >= LOSS0]
            with self.lock:
                self.new += 1
                e = min(wins, key=lambda e: e[2]) if self.args.model == "oracle" else self.rng.choice(entries)
            return {"text": move_name(e), "finish": "FAKE", "prompt": 0, "thoughts": 0, "out": 0, "secs": 0.0}
        with self.lock:
            if self.new >= self.args.max_calls:
                raise Fatal(f"call budget of {self.args.max_calls} reached; rerun with a higher --max-calls to resume")
            self.new += 1
        if self.provider != "gemini":
            return ask_other(self.provider, self.args.model, att.text(), self.max_output)
        return ask(self.args.model, att.text(), self.max_output, self.args.thinking_level)

    def decide(self, att) -> str:
        """Asks for one move in the attempt's current position, grades it against the pack, returns the move text."""
        entries = att._entries()
        used, cap = att.used, att.puzzle.cap
        pos = key(att.blue, att.red)
        k = f"{att.puzzle.index}|{used}|{pos}"
        row = self.cache.get(k)
        if row is None:
            # A child value of LOSS0 + 2n means Blue needs n more moves after this one.
            in_time = [e for e in entries if e[2] >= LOSS0 and used + 1 + (e[2] - LOSS0) // 2 <= cap]
            fastest = min(e[2] for e in entries if e[2] >= LOSS0)
            ans = self.answer(att, entries)
            if self.args.parse == "first":
                found = MOVE.findall(ans.get("head", ans["text"]))[:1]
            else:
                found = MOVE.findall(ans["text"])
            move = "-".join(found[-1]) if found else ""
            e = next((e for e in entries if move_name(e) == move), None)
            verdict = "no_answer" if not move else "illegal" if e is None else "right" if e in in_time else "wrong"
            if ans["finish"] == "refusal":  # the provider's safety filter declined: not a move at all
                move, e, verdict = "", None, "refused"
            row = {
                "k": k,
                "win_in": att.puzzle.need,
                "used": used,
                "moves_left": (fastest - LOSS0) // 2 + 1,
                "legal": len(entries),
                "right_moves": len(in_time),
                "move": move,
                "verdict": verdict,
                "value": e[2] if e else None,
                **ans,
            }
            with self.lock:
                self.cache[k] = row
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
        with self.lock:
            self.rows.append(row)
        return row["move"]

    def run(self) -> dict:
        a = self.args
        chosen = pick(eval_pool(), "probe", [2 * n - 1 for n in a.tiers], a.per_tier)
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            res = rollout(chosen, lambda group: list(pool.map(self.decide, group)), batch_size=len(chosen))
        return self.summary(res)

    def summary(self, res: dict) -> dict:
        a = self.args
        all_tiers = len(json.loads((PACKS / "manifest.json").read_text())["tiers"])
        # A fifth bin, only when the provider refused at least once, so earlier summaries stay as they were.
        verdicts = VERDICTS + ("refused",) if any(r["verdict"] == "refused" for r in self.rows) else VERDICTS

        def split(rows: list) -> dict:
            c = Counter(r["verdict"] for r in rows)
            return {
                "calls": len(rows),
                **{v: c[v] for v in verdicts},
                "chance": round(statistics.mean(r["right_moves"] / r["legal"] for r in rows), 3),
                "thinking_tokens_median": int(statistics.median(r["thoughts"] for r in rows)),
                "hit_output_limit": sum(r["finish"] == "MAX_TOKENS" for r in rows),
            }

        first = {n: split([r for r in self.rows if r["win_in"] == n and r["used"] == 0]) for n in res["by_win_in"]}
        left = {n: split([r for r in self.rows if r["moves_left"] == n]) for n in sorted({r["moves_left"] for r in self.rows})}
        out = {
            "model": a.model,
            "tag": a.tag,
            "tiers": a.tiers,
            "per_tier": a.per_tier,
            "max_output_tokens": self.max_output,
            "thinking_level": a.thinking_level or "API default",
            "puzzles_solved_by_win_in": res["by_win_in"],
            "score_these_tiers": round(res["score"], 4),
            "score_all_task_tiers": round(sum(res["by_win_in"].values()) / all_tiers, 4),
            "first_move_by_win_in": first,
            "every_move_by_moves_left": left,
            "calls_new": self.new,
            "calls_cached": len(self.rows) - self.new,
            "tokens": {t: sum(r[t] for r in self.rows) for t in ("prompt", "thoughts", "out")},
        }
        if self.provider != "gemini" and not self.fake:  # Gemini summaries keep their original shape
            out["provider"] = self.provider
        if a.parse != "last":
            out["parse"] = "first move in the answer (default: last)"
            out["thinking_tokens_reported_separately"] = not any(r.get("thinking_split") is False for r in self.rows)
        (OUT / f"{self.name}.summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

        print(f"\n{self.name}: stateless play, {a.per_tier} puzzles per tier, one fresh call per move")
        print("win-in | first move: right wrong illegal no-answer | chance | puzzles solved | thinking tokens (median)")
        for n, rate in res["by_win_in"].items():
            f = first[n]
            print(
                f"{n:>6} | {f['right']:>17} {f['wrong']:>5} {f['illegal']:>7} {f['no_answer']:>9} | "
                f"{f['chance']:>6.3f} | {rate:>14.2f} | {f['thinking_tokens_median']:>8}"
            )
        if "refused" in verdicts:
            print(f"refused by the provider's safety filter: {sum(r['verdict'] == 'refused' for r in self.rows)} calls, "
                  f"{sum(f.get('refused', 0) for f in first.values())} of them first moves")
        print(f"score over these tiers: {out['score_these_tiers']:.3f}")
        print(f"score over all {all_tiers} task tiers, deeper tiers counted as 0: {out['score_all_task_tiers']:.3f}")
        t = out["tokens"]
        print(f"calls: {out['calls_new']} new, {out['calls_cached']} cached. tokens: prompt {t['prompt']}, thinking {t['thoughts']}, answer {t['out']}")
        return out


def tiers(text: str) -> list:
    out = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="a Gemini model id, or oracle / random for a free self-test")
    ap.add_argument("--tiers", type=tiers, default=tiers("1-5"), help="win-in-N tiers, like 1-5 or 1,2,4")
    ap.add_argument("--per-tier", type=int, default=10, help="puzzles per tier (the pool has 50)")
    ap.add_argument("--workers", type=int, default=16, help="calls in flight at once")
    ap.add_argument("--max-calls", type=int, default=400, help="stop before making more new API calls than this")
    ap.add_argument("--max-output", type=int, default=0, help="output token cap; default is the model's limit, at most the task harness cap")
    ap.add_argument("--thinking-level", default=None, help="sent as thinkingLevel; leave out to use the API default")
    ap.add_argument("--provider", choices=("gemini", "anthropic", "nvidia"), default=None,
                    help="API to call; default from the model id: claude-* is anthropic, org/model is nvidia, else gemini")
    ap.add_argument("--parse", choices=("last", "first"), default="last",
                    help="which from-to move in the answer counts; first suits models that explain after the move (use with --tag)")
    ap.add_argument("--tag", default="", help="separate cache and results, for an independent repeat")
    args = ap.parse_args()
    try:
        Probe(args).run()
    except Fatal as exc:
        sys.exit(f"stopped: {exc}")


if __name__ == "__main__":
    main()
