# Thin Ice: pitch notes

Open `demo/index.html` in a browser, full screen (F11). It starts playing by itself.
**Space** pauses, **right arrow** jumps to the next scene, **left arrow** restarts the scene (twice: previous scene).
Scenes in order: 1 question, 2 game, 3 real mistake, 4 score ladder, 5 depth chart, 6 fair, 7 attacks, 8 small model, 9 command.
For a table pitch, press **space** right away to pause, then drive it with the arrows.

Numbers marked "on screen" come from `demo/data.json`; run `python demo/build_data.py` before the pitch so they are the latest.

## Five-minute table pitch (repeat five times)

Reviewers score Innovation, Impact and Implementation. Lead with why it matters, then show proof.

**0:00 to 0:45. Why it matters. Show scene 1 (question).**
- "We keep handing AI agents longer jobs: booking a trip, changing code, running a process. Every step depends on the ones before. One wrong step early and the whole job fails later."
- "So the real question is: how many steps ahead can these models actually think? Not with a calculator or a program. In their own head."
- "Today nobody can measure that cleanly. Most tests either let the model write code, or grade it with another AI, which can be wrong."

**0:45 to 1:30. The idea. Scene 2 (game).**
- "We invented a small board game, Thin Ice. Seven by six, four stones each. A stone slides until it hits something. Three in a row wins."
- "Because it is new, no model has seen it in training. And we solved it completely, all 16.5 billion positions. So for every move, we know for certain whether it is right."
- "The model gets 12 puzzles, from win-in-1 to win-in-6, against a perfect opponent. No shell, no code. It has to reason."

**1:30 to 2:30. The proof. Scene 3 (mistake). Let it play, or step with space.**
- "This is a real game from our final runs. Blue is the model, Gemini 4 Hydrogen. It has a forced win in four."
- "It plays c1-g5. The solver says: that loses, Red now wins in two. Out of 25 legal moves, exactly one kept the win: c1-a1."
- "And the same wrong move showed up in separate runs. It is not noise, it is a blind spot. Every lost puzzle gets this verdict, automatically."

**2:30 to 3:30. The result. Scenes 4 and 5.**
- Scene 4: "Score is puzzles won out of 12. Perfect play 1.000. Eighty lines of simple search that only know the rules: 0.917. The three Gemini 4 models: the numbers on screen, around half."
- Scene 5: "We also asked for one move per fresh call. Win in one or two: easy. Win in four: they almost all fall through. The horizon is about three moves."

**3:30 to 4:15. Why you can trust it. Scenes 6 and 7.**
- "Every puzzle has its own clock, two minutes per move, and every puzzle is reached. The model has the rules, notes and unlimited practice."
- "We attacked our own reward: 96 attacks plus 13 on the clock. None got through. The score is signed by the game server, the agent never touches it."

**4:15 to 5:00. It also teaches. Scenes 8 and 9.**
- "And it is a training ground, not only a test. A tiny model, Qwen3 0.6B, goes from 0.003 to 0.320 after training on the feedback practice mode gives: it learns to imitate the winning move. That is close to the Gemini 4 models in the same test."
- "Everything reproduces with one command. Questions?"

Likely questions:
- *Why no code?* "With a shell, the model writes a search program and scores 1.000. That measures programming, not planning. We tested both."
- *Is the game too artificial?* "That is the point: it is new, so nothing is memorised, and solved, so nothing is guessed. The skill, holding a forced line in your head, is general."
- *Can the model cheat?* Scene 7.

## Three-minute stage pitch (top five)

**0:00 to 0:30. Scene 1.** "AI agents are getting long jobs where every step depends on the last. How far ahead can they actually think, without a computer doing it for them? Nobody measures that cleanly. We built a way to prove it, move by move."

**0:30 to 1:00. Scene 2.** "Thin Ice: a board game we invented and solved completely, 16.5 billion positions. New, so it cannot be memorised. Solved, so every move is provably right or wrong. Twelve puzzles, a perfect opponent, no code."

**1:00 to 1:45. Scene 3.** "A real game. Gemini 4 Hydrogen, win in four. It plays c1-g5. The solver: Red now wins in two. One move out of 25 held: c1-a1. The same mistake came back in separate runs."

**1:45 to 2:20. Scenes 4 and 5.** "Simple rules-only search: 0.917. Frontier models: about half, on screen. Their horizon is about three moves: win in four is where they fall through."

**2:20 to 2:50. Scenes 7 and 8.** "The reward survived 109 attacks. And a 0.6-billion-parameter model, trained to imitate the winning moves that practice mode reveals, goes from 0.003 to 0.320."

**2:50 to 3:00. Scene 9.** "Thin Ice. Every mistake, proven. One command to reproduce it."
