"""Sliding puzzle helpers for the VisIter demo.

A sliding puzzle (generalization of the classic 15-puzzle) on a
configurable W×H grid. Tiles are numbered 1..(W*H-1), with one gap
(represented as 0). A move slides a tile adjacent to the gap into it.

Board state is a tuple of ints in row-major order, e.g. for 2×2:

    (1, 2, 3, 0)   →   1 | 2
                       --+--
                       3 | _

The gap (0) can swap with its neighbours up/down/left/right.

Because every move is reversible (slide back), the reachability graph
contains cycles — the main point of this demo.
"""

from visiter import Op, Rule


def _neighbours(pos, width, height):
    """Yield positions adjacent to *pos* on a width×height grid."""
    r, c = divmod(pos, width)
    if r > 0:
        yield pos - width   # up
    if r < height - 1:
        yield pos + width   # down
    if c > 0:
        yield pos - 1       # left
    if c < width - 1:
        yield pos + 1       # right


def _swap(board, a, b):
    """Return a new board with positions *a* and *b* swapped."""
    lst = list(board)
    lst[a], lst[b] = lst[b], lst[a]
    return tuple(lst)


def _move_label(gap_pos, tile_pos, width):
    """Human-readable label for sliding a tile into the gap."""
    diff = gap_pos - tile_pos
    if diff == width:
        return "↓"
    if diff == -width:
        return "↑"
    if diff == 1:
        return "→"
    if diff == -1:
        return "←"
    return "?"


def board_label(board, width):
    """Format a board tuple as an HTML table for Graphviz node display.

    Uses fixed-width cells for proper alignment.
    """
    height = len(board) // width
    rows = []
    for r in range(height):
        cells = []
        for c in range(width):
            val = board[r * width + c]
            display = " " if val == 0 else str(val)
            cells.append(
                f'<TD WIDTH="18" HEIGHT="18" FIXEDSIZE="TRUE">'
                f'{display}</TD>')
        rows.append(f'<TR>{"".join(cells)}</TR>')
    return f'<<TABLE BORDER="0" CELLSPACING="1" CELLPADDING="1">' \
           f'{"".join(rows)}</TABLE>>'


def make_rules(width, height):
    """Return one Rule per (gap_position, neighbour) combination.

    Each rule fires when the gap is at a specific position, and slides
    the tile from a specific neighbour into the gap. The edge label is
    an arrow showing the slide direction.
    """
    size = width * height
    rules = []
    for gap in range(size):
        for nbr in _neighbours(gap, width, height):
            label = _move_label(gap, nbr, width)
            rule_id = f"g{gap}n{nbr}"
            rules.append(Rule(
                lambda board, g=gap: board[g] == 0,
                Op(lambda board, g=gap, n=nbr: _swap(board, g, n),
                   label=label, id=rule_id),
            ))
    return rules


def goal_board(width, height):
    """The solved state: 1..N-1 then 0 (gap in bottom-right)."""
    size = width * height
    return tuple(list(range(1, size)) + [0])
