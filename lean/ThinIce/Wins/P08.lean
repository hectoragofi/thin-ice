import ThinIce.Puzzles
import ThinIce.Hints.P08

namespace ThinIce

def P08.hint : Hint := listHint Hints.P08

/-- P08: Blue, to move in the start position, has a forced win within 4 Blue moves.
Checked by `decide +kernel`. -/
theorem P08.blue_wins : ForcedWin 4 P08.blue P08.red :=
  check_sound P08.hint 4 _ _ (by decide +kernel)

end ThinIce
