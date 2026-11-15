import ThinIce.Puzzles
import ThinIce.Hints.P12

namespace ThinIce

def P12.hint : Hint := listHint Hints.P12

/-- P12: Blue, to move in the start position, has a forced win within 6 Blue moves.
Checked by `native_decide`. -/
theorem P12.blue_wins : ForcedWin 6 P12.blue P12.red :=
  check_sound P12.hint 6 _ _ (by native_decide)

end ThinIce
