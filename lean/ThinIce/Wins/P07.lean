import ThinIce.Puzzles
import ThinIce.Hints.P07

namespace ThinIce

def P07.hint : Hint := listHint Hints.P07

/-- P07: Blue, to move in the start position, has a forced win within 4 Blue moves.
Checked by `decide +kernel`. -/
theorem P07.blue_wins : ForcedWin 4 P07.blue P07.red :=
  check_sound P07.hint 4 _ _ (by decide +kernel)

end ThinIce
