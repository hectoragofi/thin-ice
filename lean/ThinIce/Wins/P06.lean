import ThinIce.Puzzles
import ThinIce.Hints.P06

namespace ThinIce

def P06.hint : Hint := listHint Hints.P06

/-- P06: Blue, to move in the start position, has a forced win within 3 Blue moves.
Checked by `decide +kernel`. -/
theorem P06.blue_wins : ForcedWin 3 P06.blue P06.red :=
  check_sound P06.hint 3 _ _ (by decide +kernel)

end ThinIce
