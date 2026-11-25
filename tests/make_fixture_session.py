#!/usr/bin/env python3
"""画面の確認用に、合成画像だけの session を作る（実際の生成物・題材は使わない）。

    uv run python tests/make_fixture_session.py /tmp/cigar-ui
    CIGAR_SESSIONS_DIR=/tmp/cigar-ui uv run tools/serve_session.py --port 8767

派生（元のカードの中に隠れる）、「説明」の理由あり / なし、足りない件数（補う）を含む。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as F  # noqa: E402

import session as S  # noqa: E402


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/cigar-ui")
    root.mkdir(parents=True, exist_ok=True)
    S.SESSIONS = root
    sdir = F.build_session(root, cards=(1, 2, 3, 4), size=6, n_ideas=6)
    state = S.load_state(sdir)
    spec = S.load_spec(sdir)
    items = S.spec_items(spec)
    # p-01 の派生を 3 件（足切りなし）。理由は、1 件目だけ AI の文、残りは方向から作る文
    for n, (iid, reason) in enumerate([("07", "元の円を大きく、数を減らした（テスト用の理由）"), ("08", ""), ("09", "")], 1):
        items.append(
            {"id": iid, "label": "derive", "direction": f"円を大きくした案 {n}", "text": F.BASE_TEXT, "seed": 9000 + n,
             "idea_id": "derive-p-01", "variant": n, "parent": "p-01", "card_note": "円を大きく", **({"reason": reason} if reason else {})}
        )
        cid = S.card_id(iid)
        F.solid(sdir / "images" / f"{cid}.png", (200 - n * 30, 90 + n * 20, 70))
        S.make_thumbs(sdir, [cid])
        state["cards"].append(cid)
        state["origin"][cid] = {"kind": "derived", "parent": "p-01"}
    S.write_json(sdir / "spec.json", spec)
    state["origin"]["p-02"] = {"kind": "kept"}
    state["round"] = 2
    state["shortfall"] = 2
    S.save_state(sdir, state)
    print(sdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
