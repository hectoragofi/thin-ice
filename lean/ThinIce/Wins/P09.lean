import ThinIce.Puzzles
import ThinIce.Hints.P09

namespace ThinIce

def P09.hint : Hint := listHint Hints.P09

/-- P09: Blue, to move in the start position, has a forced win within 5 Blue moves.
Checked by `decide +kernel`. -/
theorem P09.blue_wins : ForcedWin 5 P09.blue P09.red :=
  check_sound P09.hint 5 _ _ (by decide +kernel)

end ThinIce
