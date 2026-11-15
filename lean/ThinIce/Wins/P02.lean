import ThinIce.Puzzles
import ThinIce.Hints.P02

namespace ThinIce

def P02.hint : Hint := listHint Hints.P02

/-- P02: Blue, to move in the start position, has a forced win within 1 Blue move.
Checked by `decide +kernel`. -/
theorem P02.blue_wins : ForcedWin 1 P02.blue P02.red :=
  check_sound P02.hint 1 _ _ (by decide +kernel)

end ThinIce
