import ThinIce.Puzzles
import ThinIce.Hints.P01

namespace ThinIce

def P01.hint : Hint := listHint Hints.P01

/-- P01: Blue, to move in the start position, has a forced win within 1 Blue move.
Checked by `decide +kernel`. -/
theorem P01.blue_wins : ForcedWin 1 P01.blue P01.red :=
  check_sound P01.hint 1 _ _ (by decide +kernel)

end ThinIce
