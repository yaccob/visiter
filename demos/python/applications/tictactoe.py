"""Tic-Tac-Toe helpers for the VisIter demo.

Board state is a 9-character string, row-major order:

    positions     example
    0 1 2         X O ·
    3 4 5         · X ·
    6 7 8         O · ·

Characters: 'X', 'O', '·' (middle dot, U+00B7) for empty.

Coordinate labels follow the a–c (column) / 1–3 (row) convention:

      a   b   c
    +---+---+---+
  1 | a1| b1| c1|     positions 0, 1, 2
    +---+---+---+
  2 | a2| b2| c2|     positions 3, 4, 5
    +---+---+---+
  3 | a3| b3| c3|     positions 6, 7, 8
    +---+---+---+

Symmetry reduction: every board is normalised to its canonical form
(the lexicographically smallest among all 8 rigid symmetries of the
square — 4 rotations × 2 reflections). That way `build` merges
rotationally equivalent positions into a single node.
"""

EMPTY = "·"
COLS = "abc"
ROWS = "123"

# The 8 symmetries of the square as index permutations on a flat
# 9-element board.  Identity is included so `canonical` always has
# at least one candidate.
_SYMMETRIES = [
    (0, 1, 2, 3, 4, 5, 6, 7, 8),  # identity
    (2, 5, 8, 1, 4, 7, 0, 3, 6),  # 90° CW
    (8, 7, 6, 5, 4, 3, 2, 1, 0),  # 180°
    (6, 3, 0, 7, 4, 1, 8, 5, 2),  # 270° CW
    (2, 1, 0, 5, 4, 3, 8, 7, 6),  # flip horizontal
    (6, 7, 8, 3, 4, 5, 0, 1, 2),  # flip vertical
    (0, 3, 6, 1, 4, 7, 2, 5, 8),  # flip main diagonal
    (8, 5, 2, 7, 4, 1, 6, 3, 0),  # flip anti-diagonal
]


def canonical(board):
    """Return the lexicographically smallest symmetry of *board*."""
    return min("".join(board[i] for i in perm) for perm in _SYMMETRIES)


def current_player(board):
    """'X' moves first; players alternate."""
    return "X" if board.count("X") == board.count("O") else "O"


_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),              # diagonals
]


def has_winner(board):
    """True if X or O has three in a row."""
    for a, b, c in _LINES:
        if board[a] == board[b] == board[c] and board[a] != EMPTY:
            return True
    return False


def is_terminal(board):
    """True if the game is over (win or draw)."""
    return has_winner(board) or EMPTY not in board


def make_move(board, pos):
    """Place the current player's mark at *pos* and return canonical form."""
    b = list(board)
    b[pos] = current_player(board)
    return canonical("".join(b))


def board_label(board):
    """Format a board string as a 3×3 HTML table for node display.

    Returns a Graphviz HTML-label string (``<TABLE>…</TABLE>``).
    Fixed-width cells ensure proper alignment regardless of whether
    the font is proportional or monospaced — 'X', 'O', and '·' all
    get the same cell width.
    """
    rows = []
    for i in range(0, 9, 3):
        cells = "".join(
            f'<TD WIDTH="16" HEIGHT="16" FIXEDSIZE="TRUE">{board[i + j]}</TD>'
            for j in range(3))
        rows.append(f"<TR>{cells}</TR>")
    return f'<<TABLE BORDER="0" CELLSPACING="1" CELLPADDING="1">{"".join(rows)}</TABLE>>'


def coord(pos):
    """Return the a1–c3 coordinate label for a position index."""
    return f"{COLS[pos % 3]}{ROWS[pos // 3]}"


# Pre-built case factories so the .vit file stays concise.

def make_cases():
    """Return 9 case tuples, one per board position.

    Each case fires when the position is empty and the game isn't over.
    The op places the current player's mark and normalises to canonical
    form.  Edge labels are the a1–c3 coordinate.

    Items are ``(condition, fn, kwargs)`` tuples consumed by
    ``Builder.cases()``.
    """
    cases = []
    for pos in range(9):
        label = coord(pos)
        cases.append((
            lambda board, p=pos: board[p] == EMPTY and not is_terminal(board),
            lambda board, p=pos: make_move(board, p),
            {"label": label, "id": label},
        ))
    return cases


def make_node_label():
    """Return a ``node_label`` callback for ``to_dot``.

    The callback formats each node key (a 9-character board string)
    as an HTML table with fixed-width cells.
    """
    def _label(key, _info):
        return board_label(key)
    return _label


def empty_board():
    """Return the canonical empty board."""
    return EMPTY * 9
