# Thin Ice: pitch notes

Open `demo/index.html` in a browser, full screen (F11). It starts playing by itself.
**Space** pauses, **right arrow** jumps to the next scene, **left arrow** restarts the scene (twice: previous scene).
Scenes in order: 1 question, 2 game, 3 real mistake, 4 score ladder, 5 depth chart, 6 horizon, 7 effort, 8 fair, 9 attacks, 10 small model, 11 summary, 12 closing card.
For a table pitch, press **space** right away to pause, then drive it with the arrows.

Numbers marked "on screen" come from `demo/data.json`; run `python demo/build_data.py` before the pitch so they are the latest.

**The spine, say it at the start and at the end:** "Every model has a planning horizon. The environment measures where it is, and you can move the horizon by adding depth."

## Five-minute table pitch (repeat five times)

Reviewers score Innovation, Impact and Implementation. Lead with why it matters, then show proof.

**0:00 to 0:40. Why it matters. Scene 1 (question).**
- "We keep handing AI agents longer jobs: booking a trip, changing code, running a process. Every step depends on the ones before. One wrong step early and the job fails later."
- "So how many steps ahead can a model actually plan? Not with a program. In its own reasoning."
- "Our answer: every model has a planning horizon. Thin Ice measures where it is, and you can move the horizon by adding depth."

**0:40 to 1:15. The idea. Scene 2 (game).**
- "We invented a small board game. Seven by six, four stones each. A stone slides until it hits something. Three in a row wins."
- "It is new, so no model has seen it. And we solved it completely, all 16.5 billion positions, so every move has an exact verdict. No judge model, no partial credit."
- "12 puzzles, win in 1 up to win in 6, against a perfect opponent. No shell, no code."

**1:15 to 2:00. The proof. Scene 3 (mistake).**
- "A real game. Gemini 4 Hydrogen, win in four. It plays c1-g5. The solver: that loses, Red now wins in two. Out of 25 legal moves, exactly one kept the win: c1-a1."
- "This is not one bad run. The same move came up in 27 runs, across 7 models (on screen). It is a blind spot, and every lost puzzle is graded like this."

**2:00 to 2:50. Where the horizon is. Scenes 4 and 5.**
- Scene 4: "Score is puzzles won out of 12. Perfect play 1.000. Eighty lines of search that only know the rules: 0.917. Ten models, 101 runs. Best over many runs: Gemini 4 Carbon, 0.593 over 17. Claude Fable 5.2 got 0.750 in one run: a data point, not a rank. Nemotron 3 Ultra at the bottom, 0.194."
- Scene 5: "Here is where it breaks. Over all 49 Gemini 4 runs: win in 1 and 2, 97 of 98. Win in 3, 76. Win in 4, 43. Win in 5 and 6, 7 each. The horizon is about three moves."

**2:50 to 3:30. Moving the horizon. Scenes 6 and 7.**
- "Then we added depth: a variant with win in 7, 8 and 9. Claude Opus 5.5: 0 of 12. Gemini 4 Carbon: 0 of 18. The solver: 6 of 6."
- "Look at Fable's row: perfect up to win in 4, then 1 of 4. Each model has a depth where it stops, and the environment shows exactly where."

**3:30 to 4:10. Why you can trust it. Scenes 8 and 9.**
- "Is it the clock? No. Of 261 puzzles Gemini 4 lost, 258 were moves the solver proves wrong. 3 ran out of time. The rules, notes and unlimited practice are always there."
- "We attacked our own reward: 96 attacks plus 13 on the clock. None got through. The score sheet is signed by the game server."

**4:10 to 5:00. Can a model learn here? Scene 10, then scene 11 (summary, let it play) and 12.**
- "Practising inside a session does not help: we told Haiku, Argon and Carbon to practise first, and every change was within one puzzle."
- "Training does. A tiny model, Qwen3 0.6B, one move per call on held-out puzzles: 0.003 untrained, 0.320 trained on the winning moves, 0.207 from the reward bit alone. Gemini 4 scores 0.40 to 0.52 in that same one-move setting."
- "Every model has a planning horizon. Thin Ice measures where it is, and you can move the horizon by adding depth. One command reproduces it. Questions?"

### Likely questions

- *You removed code. Isn't that withholding tools?* "The organisers confirmed the config change is allowed. With code, the task is solved by an 80-line search, so it would measure programming. Everything else is there: the rules, the legal moves, notes, unlimited practice with the right answer."
- *The reference uses a solver and the agent may not.* "The solver is the grader: it proves each win exists and judges every move. The second reference is 80 lines that know only the rules, no solver, and it scores 0.917."
- *Is it the clock?* "No. 258 of the 261 puzzles Gemini 4 lost were wrong moves the solver proves; 3 ran out of time."
- *What if the model tries harder?* "We tested it. Same task, reasoning effort set to high: Gemini 4 Carbon and Claude Opus 5.5 both go to 11 of 12 on wins 3 to 4 moves away, from about 70% and 50%. On wins 5 to 6 moves away they score 0 and 1 of 12. Carbon at low effort drops to 0.500, default is 0.593, high is 0.639. More thinking moves the middle, not the edge. Side experiment, 3 runs per setting."
- *Does a bigger model see further?* "Not by default. Claude Haiku 5.5 at about 13 cents a run scores 0.500; Opus 5.5 at about $3.30 scores 0.531. And a trained Qwen3-4B (0.280 at 200k examples) is barely ahead of the 0.6B (0.223) and 1.7B (0.260) at the same point."
- *Can a model learn here?* "Training, yes: Qwen3 0.6B goes from 0.003 to 0.320 in the one-move setting. In-session practice, no: every change within one puzzle."
- *Why so few Claude runs?* "Gemini has 14 to 18 runs per model. Opus has 8, Haiku and Sonnet 5 have 3, Fable 1, so those are indicative. Sonnet 5.5 refused the task at the provider; Mistral Large 4 was too slow for the move clock, so neither is scored."
- *Is the game too artificial?* "That is the point: new, so nothing is memorised; solved, so nothing is guessed. The skill, holding a forced line in your head, is general."
- *Can the model cheat?* Scene 9.

## Three-minute stage pitch (top five)

**0:00 to 0:25. Scene 1.** "AI agents get long jobs where every step depends on the last. How far ahead can they plan without a computer doing it? Every model has a planning horizon. We built the environment that measures where it is."

**0:25 to 0:50. Scene 2.** "Thin Ice: a board game we invented and solved completely, 16.5 billion positions. New, so nothing is memorised. Solved, so every move is provably right or wrong. Twelve puzzles, a perfect opponent, no code."

**0:50 to 1:20. Scene 3.** "A real game. Gemini 4 Hydrogen, win in four. It plays c1-g5. The solver: Red now wins in two. One move of 25 held. The same move came up in 27 runs across 7 models."

**1:20 to 2:00. Scenes 4 and 5.** "Rules-only search: 0.917. Ten models: 0.194 to 0.750, the best over many runs 0.593. Over 49 Gemini 4 runs, win in 2 is nearly always won, win in 5 almost never. The horizon is about three moves."

**2:00 to 2:30. Scenes 6 and 7.** "Add depth, win in 7 to 9: Opus 5.5 0 of 12, Gemini 4 Carbon 0 of 18, the solver 6 of 6. The horizon moves, and the environment shows exactly where."

**2:30 to 2:45. Scenes 8 and 10.** "258 of 261 losses are wrong moves, not the clock. Practising inside a session does not help; training does: a 0.6B model goes from 0.003 to 0.320 in the one-move setting."

**2:45 to 3:00. Scene 11 (summary), then 12.** "Every model has a planning horizon. Thin Ice measures where it is, and you can move it by adding depth. One command reproduces it."
