import ThinIce.Puzzles
import ThinIce.Hints.P10

namespace ThinIce

def P10.hint : Hint := listHint Hints.P10

/-- P10: Blue, to move in the start position, has a forced win within 5 Blue moves.
Checked by `decide +kernel`. -/
theorem P10.blue_wins : ForcedWin 5 P10.blue P10.red :=
  check_sound P10.hint 5 _ _ (by decide +kernel)

end ThinIce
