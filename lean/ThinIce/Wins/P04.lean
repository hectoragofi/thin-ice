import ThinIce.Puzzles
import ThinIce.Hints.P04

namespace ThinIce

def P04.hint : Hint := listHint Hints.P04

/-- P04: Blue, to move in the start position, has a forced win within 2 Blue moves.
Checked by `decide +kernel`. -/
theorem P04.blue_wins : ForcedWin 2 P04.blue P04.red :=
  check_sound P04.hint 2 _ _ (by decide +kernel)

end ThinIce
