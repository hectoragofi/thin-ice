import ThinIce.Puzzles
import ThinIce.Hints.P03

namespace ThinIce

def P03.hint : Hint := listHint Hints.P03

/-- P03: Blue, to move in the start position, has a forced win within 2 Blue moves.
Checked by `decide +kernel`. -/
theorem P03.blue_wins : ForcedWin 2 P03.blue P03.red :=
  check_sound P03.hint 2 _ _ (by decide +kernel)

end ThinIce
