/-!
# Thin Ice: the rules

A hand-written copy of `thinice/board.py`. Squares are numbered `row * 7 + column` from 0,
with a1 = 0 in the bottom-left corner; a set of stones is a bitmask over those 42 squares.
-/
namespace ThinIce

/-- A set of stones: bit `sq` is set iff a stone stands on square `sq`. -/
abbrev Mask := Nat

/-- A position: Blue's stones and Red's stones. Whose turn it is is tracked by the caller. -/
structure Pos where
  blue : Mask
  red : Mask
deriving Repr, DecidableEq

def maskOf (sqs : List Nat) : Mask := sqs.foldl (fun m s => m ||| (1 <<< s)) 0

def ofSquares (b r : List Nat) : Pos := ⟨maskOf b, maskOf r⟩

def has (m : Mask) (sq : Nat) : Bool := m.testBit sq

/-- The 8 directions as (dx, dy), in `board.py`'s order. -/
def dirs : List (Int × Int) := [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]

def onBoard (x y : Int) : Bool := 0 ≤ x && x < 7 && 0 ≤ y && y < 6

def sqAt (x y : Int) : Nat := (y * 7 + x).toNat

/-- Slide from (x, y) in direction (dx, dy) over the occupied set `occ`: the stone keeps going
while the next cell is on the board and empty. `fuel` bounds the steps (6 is the most possible). -/
def slide (occ : Mask) : Nat → Int → Int → Int → Int → Nat
  | 0, x, y, _, _ => sqAt x y
  | fuel + 1, x, y, dx, dy =>
    if onBoard (x + dx) (y + dy) && !has occ (sqAt (x + dx) (y + dy)) then
      slide occ fuel (x + dx) (y + dy) dx dy
    else sqAt x y

/-- Legal moves `(from, to)` for the stones `mine`, with `occ` all occupied squares.
A stone must move at least one cell. (Same set as `board.moves`; Python also sorts the list.) -/
def moves (mine occ : Mask) : List (Nat × Nat) :=
  (List.range 42).flatMap fun sq =>
    if has mine sq then
      dirs.filterMap fun d =>
        let t := slide occ 7 ((sq % 7 : Nat) : Int) ((sq / 7 : Nat) : Int) d.1 d.2
        if t = sq then none else some (sq, t)
    else []

/-- Every three-in-a-row on the board, as a mask of its three cells. -/
def lines : List Mask :=
  (List.range 42).flatMap fun sq =>
    let x : Int := ((sq % 7 : Nat) : Int)
    let y : Int := ((sq / 7 : Nat) : Int)
    ([(1, 0), (0, 1), (1, 1), (1, -1)] : List (Int × Int)).filterMap fun d =>
      let cells := ([0, 1, 2] : List Int).map fun i => (x + d.1 * i, y + d.2 * i)
      if cells.all (fun c => onBoard c.1 c.2) then
        some (maskOf (cells.map fun c => sqAt c.1 c.2))
      else none

/-- The stones `m` contain three in a row. -/
def hasLine (m : Mask) : Bool := lines.any fun l => m &&& l == l

/-- Move one stone of `mine` from `mv.1` to `mv.2`. -/
def play (mine : Mask) (mv : Nat × Nat) : Mask := mine ^^^ (1 <<< mv.1) ^^^ (1 <<< mv.2)

/-! ## What a forced win is

`ForcedWin n me opp`: the side to move, with stones `me` against `opp`, can force three in a
row within `n` of its own moves, whatever the opponent does. This is the specification; it says
nothing about how a win is found. -/
inductive ForcedWin : Nat → Mask → Mask → Prop
  /-- A legal move makes three in a row at once. -/
  | now {n me opp} (m : Nat × Nat) :
      m ∈ moves me (me ||| opp) → hasLine (play me m) = true → ForcedWin (n + 1) me opp
  /-- A legal move after which every opponent reply fails to make the opponent's line and leaves
  a forced win in `n`. If the opponent has no legal move, it loses, which this case covers. -/
  | later {n me opp} (m : Nat × Nat) :
      m ∈ moves me (me ||| opp) →
      (∀ r ∈ moves opp (play me m ||| opp), hasLine (play opp r) = false) →
      (∀ r ∈ moves opp (play me m ||| opp), ForcedWin n (play me m) (play opp r)) →
      ForcedWin (n + 1) me opp

/-! ## The checker

`check hint n me opp` searches for a forced win. At each node it first looks for a move that wins
at once; otherwise it tries the hinted move only (if the hint names a legal move), or every legal
move when there is no hint. Hints come from an untrusted search; a wrong hint can only make the
check fail. `check_sound` below proves that `check` returning `true` implies `ForcedWin`. -/

abbrev Hint := Mask → Mask → Nat → Option (Nat × Nat)

def noHint : Hint := fun _ _ _ => none

def candidates (hint : Hint) (me opp : Mask) (n : Nat) (ms : List (Nat × Nat)) : List (Nat × Nat) :=
  match hint me opp n with
  | some m => ms.filter (· == m)
  | none => ms

def check (hint : Hint) : Nat → Mask → Mask → Bool
  | 0, _, _ => false
  | n + 1, me, opp =>
    (moves me (me ||| opp)).any (fun m => hasLine (play me m)) ||
    (candidates hint me opp (n + 1) (moves me (me ||| opp))).any fun m =>
      (moves opp (play me m ||| opp)).all fun r =>
        !hasLine (play opp r) && check hint n (play me m) (play opp r)

/-- The moves of the side to move that keep a forced win within `n + 1` (exhaustive, no hints). -/
def winningMoves (n : Nat) (me opp : Mask) : List (Nat × Nat) :=
  (moves me (me ||| opp)).filter fun m =>
    hasLine (play me m) ||
    (moves opp (play me m ||| opp)).all fun r =>
      !hasLine (play opp r) && check noHint n (play me m) (play opp r)

/-! ## Hint tables -/

/-- Look a node up in a list of `((me, opp, n), move)` hints. -/
def listHint (l : List ((Nat × Nat × Nat) × (Nat × Nat))) : Hint :=
  fun b r k => (l.find? (fun e => e.1 == (b, r, k))).map (·.2)

/-! ## Soundness of the checker -/

theorem check_sound (hint : Hint) : ∀ n me opp, check hint n me opp = true → ForcedWin n me opp := by
  intro n
  induction n with
  | zero => intro me opp h; simp [check] at h
  | succ n ih =>
    intro me opp h
    simp only [check, Bool.or_eq_true, List.any_eq_true] at h
    rcases h with ⟨m, hm, hl⟩ | ⟨m, hc, hall⟩
    · exact ForcedWin.now m hm hl
    · have hm : m ∈ moves me (me ||| opp) := by
        unfold candidates at hc
        split at hc
        · exact (List.mem_filter.mp hc).1
        · exact hc
      have key : ∀ r ∈ moves opp (play me m ||| opp),
          hasLine (play opp r) = false ∧ check hint n (play me m) (play opp r) = true := by
        intro r hr
        have := (List.all_eq_true.mp hall) r hr
        simpa only [Bool.and_eq_true, Bool.not_eq_true'] using this
      exact ForcedWin.later m hm (fun r hr => (key r hr).1) (fun r hr => ih _ _ (key r hr).2)

end ThinIce
