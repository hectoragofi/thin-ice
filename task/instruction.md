# Thin Ice

You play Blue in **Thin Ice**, a two-player board game. These are the complete rules.

- **Board:** 7 columns by 6 rows. Columns `a`-`g` (left to right), rows `1`-`6` (bottom to top). `a1` is the bottom-left corner.
- **Stones:** Blue has 4, Red has 4. Players alternate. A turn moves exactly one of your own stones.
- **Move:** pick a stone and one of the 8 directions (up, down, left, right, 4 diagonals). The stone slides in that direction and cannot stop early: it stops only on the last empty cell before the edge of the board or before another stone. It must move at least one cell. Stones never jump, capture or push.
- **Win:** the first player whose stones have 3 in a row (adjacent cells in a horizontal, vertical or diagonal line) after their own move wins at once. A player with no legal move on their turn loses.
- **Notation:** `from-to`. `a1-a6` means the stone on a1 slid up until it stopped on a6.

## Your task

There are 32 puzzles, `P01` to `P32`. In each one it is Blue's turn and Blue has a forced win: a way to make 3 in a row no matter what Red does. Red is played by a perfect opponent that always picks the longest defence.

**Win as many puzzles as you can. Your score is the number of puzzles won divided by 32.**

- Each puzzle states how many Blue moves the forced win takes (`win in N`). You are allowed N+1 moves.
- A puzzle is lost the moment you play a move after which the win is no longer forced, or when your moves run out. There is no undo and no second attempt.
- Puzzles come one at a time, in order: only the current puzzle can be viewed and played, and the next one unlocks when it is won or lost. They get harder: `P01`-`P02` are a win in 1 move, `P31`-`P32` a win in 16. `skip_puzzle` gives up the current puzzle (it counts as lost) and moves on.
- You have 30 minutes in total.

## How to play

MCP server `thin-ice`: `rules`, `list_puzzles`, `show_puzzle`, `play_move`, `new_practice_puzzle`, `save_note`, `skip_puzzle`. These are your only tools for the game.

**This is a test of your own look-ahead.** There is no shell, no file writing and no way to run code, so you cannot write a search program: you work out each move by thinking it through. Reading files is allowed but there is nothing about the game on disk.

**Every reply must end in a tool call.** A reply that ends without one (including a reply cut off because it ran past the model's output limit, thinking included) ends your session for good, and puzzles you have not reached then score nothing. Long analysis is fine, but spread it over many turns:

1. Look at the puzzle (`show_puzzle`) and pick one or two candidate moves.
2. Check one candidate against Red's replies for a while, then save what you found with `save_note`: which replies you have answered, which are still open, your verdict so far. Notes come back with `show_puzzle`.
3. Continue in the next turn from your notes. Play the move (`play_move`) once every Red reply is answered.

Think in steps of a few paragraphs, not one long stretch. A saved note keeps your work; an unfinished thought is lost with the session.

## Practice

`new_practice_puzzle` gives you a fresh puzzle that never counts. When you get a practice move wrong it tells you which move would have won. Use practice as much as you like, to learn how the stones slide and how forced wins are built.
