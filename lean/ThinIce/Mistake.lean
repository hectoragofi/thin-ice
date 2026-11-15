import ThinIce.Puzzles

/-!
# A showcased mistake: P07, Blue plays c1-g5

In P07 (Blue on 2, 7, 30, 32; Red on 6, 16, 17, 25; Blue to move), Blue's c1-g5 (square 2 to
square 34) is legal and does not win at once, and afterwards Red, to move, has a forced win within
2 Red moves. Red's moves that keep that win are exactly c3-e1 (16 to 4) and d3-f1 (17 to 5).
Plain exhaustive search, no hints, checked by the kernel (`decide +kernel`), no `native_decide`.
-/

namespace ThinIce

/-- Blue's stones after c1-g5. -/
def P07.afterC1G5 : Mask := play P07.blue (2, 34)

theorem P07.c1g5_legal : (2, 34) ∈ moves P07.blue (P07.blue ||| P07.red) := by decide +kernel

theorem P07.c1g5_no_line : hasLine P07.afterC1G5 = false := by decide +kernel

/-- After c1-g5, Red (to move) forces three in a row within 2 Red moves. -/
theorem P07.c1g5_loses : ForcedWin 2 P07.red P07.afterC1G5 :=
  check_sound noHint 2 _ _ (by decide +kernel)

/-- Red's winning first moves are exactly c3-e1 and d3-f1. -/
theorem P07.red_winning_moves : winningMoves 1 P07.red P07.afterC1G5 = [(16, 4), (17, 5)] := by
  decide +kernel

end ThinIce
