# Thin Ice

You play Blue in **Thin Ice**, a two-player board game. These are the complete rules.

- **Board:** 7 columns by 6 rows. Columns `a`-`g` (left to right), rows `1`-`6` (bottom to top). `a1` is the bottom-left corner.
- **Stones:** Blue has 4, Red has 4. Players alternate. A turn moves exactly one of your own stones.
- **Move:** pick a stone and one of the 8 directions (up, down, left, right, 4 diagonals). The stone slides in that direction and cannot stop early: it stops only on the last empty cell before the edge of the board or before another stone. It must move at least one cell. Stones never jump, capture or push.
- **Win:** the first player whose stones have 3 in a row (adjacent cells in a horizontal, vertical or diagonal line) after their own move wins at once. A player with no legal move on their turn loses.
- **Notation:** `from-to`. `a1-a6` means the stone on a1 slid up until it stopped on a6.

## Your task

There are 10 puzzles, `P01` to `P10`. In each one it is Blue's turn and Blue has a forced win: a way to make 3 in a row no matter what Red does. Red is played by a perfect opponent that always picks the longest defence.

**Win as many puzzles as you can. Your score is the number of puzzles won divided by 10.**

- Each puzzle states how many Blue moves the forced win takes (`win in N`). You are allowed N+1 moves.
- A puzzle is lost the moment you play a move after which the win is no longer forced, or when your moves run out. There is no undo and no second attempt.
- Puzzles are independent and can be played in any order. They get harder: `P01` is a win in 2 moves, `P02` a win in 3, `P03`-`P04` a win in 4, `P05`-`P06` in 5, `P07`-`P08` in 6 and `P09`-`P10` in 7. `list_puzzles` shows each one. Every puzzle can be won with the look-ahead tools below, within the look-ahead budget and the time limit.
- You have 150 minutes in total. Unfinished puzzles count as not won.
- Each of your turns has an output limit. A single very long stretch of thinking without a tool call can hit it, and then the session ends there, with every unfinished puzzle counting as not won. Work in small steps: think a little, check it with a tool, and continue.

## What you can use

This is a test of planning by reasoning. You cannot run code: there is no shell, you cannot write files, and there are no subagents and no web access. You play with the game's tools (MCP server `thin-ice`) and your own thinking. You may also read files and keep a todo list, but nothing in this container helps with the game.

Playing:

- `rules`, `list_puzzles`, `show_puzzle(puzzle_id)`
- `play_move(puzzle_id, move)`: plays one Blue move for real. Red replies at once. No undo.
- `new_practice_puzzle(win_in)`: a fresh puzzle that never counts. When you get a practice move wrong it tells you which move would have won.

Looking ahead (nothing is played, no puzzle changes, but it costs look-ahead budget):

- `explore_position(puzzle_id, moves)`: applies a move sequence to the puzzle's current position (Blue first, then alternating, space separated, for example `"f3-f4 c5-c1"`; empty for none) and shows the board, whose turn it is, the legal moves of the side to move, and for each colour the moves that would make three in a row on its turn (for the side not to move, that is what it threatens).
- `explore_lines(puzzle_id, lines)`: the same for up to 40 sequences at once, one compact row per sequence.

The look-ahead tools apply the rules and nothing else. They never tell you whether a position is winning, how Red would answer, or which move to play: working that out is the task. They work on open puzzles, scored and practice.

**Look-ahead budget: 4000 explored positions for the whole run.** Every `explore_position` call costs 1 and every `explore_lines` call costs 1 per line you send (illegal lines included). The budget is shared by all puzzles, scored and practice alike, and it never refills. Every look-ahead answer and `list_puzzles` show how much is left. A request larger than what is left is refused whole and costs nothing. When the budget is used up the look-ahead tools refuse, but `play_move`, `show_puzzle` and the rest still work. Puzzles can be played in any order, so you decide how much of the budget each one deserves. (If a run is set up with a different budget or a deeper top tier, `list_puzzles` shows the actual budget and puzzles.)
