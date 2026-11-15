import ThinIce.Puzzles
import ThinIce.Hints.P11

namespace ThinIce

def P11.hint : Hint := listHint Hints.P11

/-- P11: Blue, to move in the start position, has a forced win within 6 Blue moves.
Checked by `decide +kernel`. -/
theorem P11.blue_wins : ForcedWin 6 P11.blue P11.red :=
  check_sound P11.hint 6 _ _ (by decide +kernel)

end ThinIce
