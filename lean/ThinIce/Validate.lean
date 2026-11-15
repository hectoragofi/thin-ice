import ThinIce.Puzzles

/-!
# Do the Lean rules match `board.py`?

For each of the 12 start positions, Lean's list of legal Blue moves is the same set as the one
`board.moves` printed (exported by `tools/lean_export.py`), and neither side starts with a line.
-/

namespace ThinIce

/-- Same set of moves, same count, as Python, and no line on the board at the start. -/
def matchesPython (p : Pos) (py : List (Nat × Nat)) (count : Nat) : Bool :=
  let lm := moves p.blue (p.blue ||| p.red)
  lm.length == count && py.length == count && py.all (· ∈ lm) && lm.all (· ∈ py) &&
  !hasLine p.blue && !hasLine p.red && (p.blue &&& p.red) == 0

theorem rules_match_python :
    matchesPython P01 P01.pyMoves P01.blueMoves && matchesPython P02 P02.pyMoves P02.blueMoves &&
    matchesPython P03 P03.pyMoves P03.blueMoves && matchesPython P04 P04.pyMoves P04.blueMoves &&
    matchesPython P05 P05.pyMoves P05.blueMoves && matchesPython P06 P06.pyMoves P06.blueMoves &&
    matchesPython P07 P07.pyMoves P07.blueMoves && matchesPython P08 P08.pyMoves P08.blueMoves &&
    matchesPython P09 P09.pyMoves P09.blueMoves && matchesPython P10 P10.pyMoves P10.blueMoves &&
    matchesPython P11 P11.pyMoves P11.blueMoves && matchesPython P12 P12.pyMoves P12.blueMoves = true := by
  decide +kernel

/-- P07 has 25 legal Blue moves, as `board.py` says. -/
theorem P07.blue_move_count : (moves P07.blue (P07.blue ||| P07.red)).length = 25 := by decide +kernel

end ThinIce
