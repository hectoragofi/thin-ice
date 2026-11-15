# Can the score be gamed?

The attacks we tried on our own reward, what stops each one, and the Lean proofs of the 12 scored puzzles. Summary in the [README](../README.md).

The reward is the number of puzzles won against a perfect opponent, so the only way to raise it is to play winning moves.

| attack | what stops it |
|---|---|
| Do nothing, or stop early | 0 for nothing; 1/12 per puzzle actually won |
| Guess | A puzzle dies on the first non-winning move. Random play scores 0.00 - 0.08 |
| Retry, undo, reset | Not in the API. State lives in the game server and only moves forward |
| Write a program anyway | The agent has no tool that can write files or run code, so it cannot install a config or pick another agent, and Harbor always runs OpenCode's default build agent. A root-owned managed OpenCode config (`/etc/opencode/opencode.json`) denies shell, file editing, file writing, web fetch and web search, and subagents inherit the denials. Someone with a shell in the container could define a new OpenCode agent with those tools; the agent has no shell |
| Use `save_note` for something else | A note is the agent's own text, kept in the game server's memory for that run only and shown back by `show_puzzle`. The server never reads it, it is not on the score sheet, and it is capped (4,000 characters, 100 per puzzle, 2,000 in total). It only lets a long analysis span several turns |
| Peek at or play ahead on later puzzles | Locked until the current puzzle is won, lost or skipped; viewing or moving on a locked puzzle is refused, under any spelling of its id. A skip counts as lost and cannot be undone |
| Beat the clock | A move after the puzzle's clock is refused and the puzzle is lost. The clock is server time, starts at the first look and cannot be restarted by re-reading, practising, skipping or another spelling of the id |
| Read the answers | Puzzles, opponent and solutions live in a separate container. The agent's container holds none of the game's code or data |
| Learn the scored puzzles in practice | All published puzzles, scored and practice, are mutually disjoint: no position reachable in one occurs in any other, up to rotation and reflection. The build fails if two share a position |
| Edit the score | The verifier reads one file: a score sheet written and HMAC-signed by the game server, mounted read-only into the agent's container. The key never exists in the agent's sandbox. The key file is in this repo (`task/environment/game-server/receipt.key`, `task/tests/receipt.key`) because the game server and verifier need it; the agent has no web access, so it cannot read it during a run |
| Tamper with the grader | Verification runs in a separate container that the agent never touches. The agent itself is not root |
| Break the verifier's input | A missing, malformed or mis-signed score sheet scores 0 |

`python tools/redteam.py <server url>` runs the attack suite against a live game server: 96 checks, all passing, including the puzzle lock and `skip_puzzle`; `--clock` adds 13 attacks on the clock (also run from inside the agent's container on local Docker: 96 of 96, and 12 of 13 on the clock; the one miss was the check rounding 29.x seconds down, fixed in the check, not the server) (late winning moves under three id spellings, skip after expiry, re-looking, practice), all refused. The note tool was attacked through a real MCP client (locked puzzles, oversized notes, a fake score written into a note, the caps): the score and the signed receipt never change. In every agent run we read, notes contain only game analysis and no agent touched a non-game tool.

## The puzzles are proven, not just solved

Twelve scored puzzles also come with machine-checked proofs, in Lean 4 (`lean/`, build with `lake build`). Lean has its own copy of the rules. For each of the 12 puzzles the server serves with seed "1", it proves that Blue has a forced win within the stated number of moves. For puzzle P07, it proves that the mistake c1-g5 lets Red force a win within two moves, and that c3-e1 and d3-f1 are Red's only winning first moves. The winning strategies come from an untrusted search, but Lean re-checks every move and every Red reply itself. Eleven of the twelve are checked by Lean's kernel alone; the last (P12) also trusts the Lean compiler (`native_decide`). Not proven: that these wins are the fastest, that a move is the only one that holds (except the P07 line), anything about draws, or the solved game as a whole. That the Lean rules match `board.py` is checked against Python on these positions, not proven.

Building the proofs is optional and not part of the one-command evaluation; it needs elan and Lean 4.35.0 (pinned in `lean/lean-toolchain`). Writing them turned up one gap in the rules-only search reference: `thinice/search.py` does not count a win when Blue's last allowed move leaves Red with no legal move, which the rules score as a loss for Red. It changes no result on these 12 puzzles, and the task is frozen, so it is noted here rather than fixed.
