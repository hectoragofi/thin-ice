# Thin Ice

You play Blue in **Thin Ice**, a two-player board game. These are the complete rules.

- **Board:** 5x5. Columns `a`-`e` (left to right), rows `1`-`5` (bottom to top). `a1` is the bottom-left corner.
- **Stones:** Blue has 4, Red has 4. Players alternate. A turn moves exactly one of your own stones.
- **Move:** pick a stone and one of the 8 directions (up, down, left, right, 4 diagonals). The stone slides in that direction and cannot stop early: it stops only on the last empty cell before the edge of the board or before another stone. It must move at least one cell. Stones never jump, capture or push.
- **Win:** the first player whose stones have 3 in a row (adjacent cells in a horizontal, vertical or diagonal line) after their own move wins at once. A player with no legal move on their turn loses.
- **Notation:** `from-to`. `a1-a5` means the stone on a1 slid up until it stopped on a5.

## Your task

There are 24 puzzles, `P01` to `P24`. In each one it is Blue's turn and Blue has a forced win: a way to make 3 in a row no matter what Red does. Red is played by a perfect opponent that always picks the longest defence.

**Win as many puzzles as you can. Your score is the number of puzzles won divided by 24.**

- Each puzzle states how many Blue moves the forced win takes (`win in N`). You are allowed N+1 moves.
- A puzzle is lost the moment you play a move after which the win is no longer forced, or when your moves run out. There is no undo and no second attempt.
- Puzzles are independent and can be played in any order. They get harder: `P01`-`P02` are a win in 1 move, `P23`-`P24` a win in 12.
- You have 30 minutes in total.

## How to play

MCP server `thin-ice`: `rules`, `list_puzzles`, `show_puzzle`, `play_move`, `new_practice_puzzle`.

The same actions from the shell: `ice list`, `ice show P01`, `ice move P01 a1-a5`, `ice practice 3` (add `--json` for JSON). `ice api` describes the HTTP API if you want to call the game from your own programs.

## Practice

`new_practice_puzzle` (or `ice practice N`) gives you a fresh puzzle that never counts. When you get a practice move wrong it tells you which move would have won. Use practice as much as you like, to learn the game or to check your own tools against it.

You may use anything in this container. Python 3 is installed.
