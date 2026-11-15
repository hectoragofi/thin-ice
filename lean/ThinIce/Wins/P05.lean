import ThinIce.Puzzles
import ThinIce.Hints.P05

namespace ThinIce

def P05.hint : Hint := listHint Hints.P05

/-- P05: Blue, to move in the start position, has a forced win within 3 Blue moves.
Checked by `decide +kernel`. -/
theorem P05.blue_wins : ForcedWin 3 P05.blue P05.red :=
  check_sound P05.hint 3 _ _ (by decide +kernel)

end ThinIce
