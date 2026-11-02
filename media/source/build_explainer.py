# ruff: noqa: E501, D103, S603, S607
"""Generate the Hyperframes compositions for the topic explainers (data pipelines, Kafka).

Each explainer shares the architecture video's look: title, a concept scene, the system
map lit one group at a time, fact cards, a where-in-the-code scene, and the end card.
Narration timings come from the measured WAV lengths in assets/vo.

Usage: python3 build_explainer.py <pipelines|kafka>

It runs from the published media/source folder (architecture-explained, data-pipelines-explained,
kafka-explained) or from the working folder it was written in (tallyproof-<name>).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDERS = {
    "architecture": ("architecture-explained", "tallyproof-architecture"),
    "pipelines": ("data-pipelines-explained", "tallyproof-pipelines"),
    "kafka": ("kafka-explained", "tallyproof-kafka"),
}


def composition_dir(which: str) -> Path:
    for name in FOLDERS[which]:
        if (HERE / name / "composition").exists():
            return HERE / name / "composition"
    raise SystemExit(f"no composition folder for {which} beside {HERE}")


ARCH = composition_dir("architecture")
GAP = 0.5  # seconds of silence between narration lines
LEAD = 0.4  # narration starts this long after its scene


def wav_len(p: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return float(out)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- scene templates


def title_scene(label: str, dur: float) -> str:
    t = (ARCH / "compositions" / "title.html").read_text()
    t = t.replace("How it works, in about a minute", esc(label))
    t = t.replace('data-duration="8.6"', f'data-duration="{dur}"')
    t = t.replace("      8.3,\n", f"      {dur - 0.3:.2f},\n")
    t = t.replace("      1.4,\n", "      0.8,\n").replace(
        '{ opacity: 1, duration: 0.35, ease: "power2.out" }, 3.2);',
        '{ opacity: 1, duration: 0.35, ease: "power2.out" }, 1.1);',
    )
    return t


def outro_scene(dur: float) -> str:
    t = (ARCH / "compositions" / "outro.html").read_text()
    return t.replace('data-duration="4.4"', f'data-duration="{dur}"')


def map_scene(steps: list[dict], dur: float, label: str) -> str:
    """The architecture map with a custom step list. Each step: at, dur, boxes, wires, cap, labels?, boundary?"""
    t = (ARCH / "compositions" / "map.html").read_text()
    t = t.replace("How Tallyproof works", esc(label))
    t = t.replace('data-duration="57.1"', f'data-duration="{dur}"')
    # captions
    start = t.index('      <div class="cap" id="cap-2">')
    end = t.index("    </div>\n  </div>\n  <script>")
    caps = "".join(
        f'      <div class="cap" id="cap-{i}">{s["cap"]}</div>\n' for i, s in enumerate(steps, 1)
    )
    t = t[:start] + caps + t[end:]
    # steps
    start = t.index("    const steps = [")
    end = t.index("    ];\n", start) + len("    ];\n")
    js = "    const steps = [\n"
    for i, s in enumerate(steps, 1):
        extra = ""
        if s.get("labels"):
            extra += f", labels: {json.dumps(s['labels'])}"
        if s.get("boundary"):
            extra += ", boundary: true"
        js += (
            f"      {{ at: {s['at']}, dur: {s['dur']}, boxes: {json.dumps(s['boxes'])}, "
            f'wires: {json.dumps(s["wires"])}{extra}, cap: "#cap-{i}" }},\n'
        )
    js += "    ];\n"
    t = t[:start] + js + t[end:]
    t = t.replace(
        'tl.to(prev.wires.map((w) => "#flow-" + w).join(", "), { opacity: 0, duration: 0.3 }, s.at);',
        'if (prev.wires.length) tl.to(prev.wires.map((w) => "#flow-" + w).join(", "), { opacity: 0, duration: 0.3 }, s.at);',
    )
    t = t.replace(
        "tl.fromTo(flows, { opacity: 0, strokeDashoffset: 0 }, { opacity: 1, duration: 0.4, immediateRender: false }, s.at + 0.1);",
        "if (flows) tl.fromTo(flows, { opacity: 0, strokeDashoffset: 0 }, { opacity: 1, duration: 0.4, immediateRender: false }, s.at + 0.1);",
    )
    t = t.replace(
        'tl.fromTo(flows, { strokeDashoffset: 0 }, { strokeDashoffset: -26 * Math.round(s.dur * 6), duration: s.dur, ease: "none", immediateRender: false }, s.at + 0.1);',
        'if (flows) tl.fromTo(flows, { strokeDashoffset: 0 }, { strokeDashoffset: -26 * Math.round(s.dur * 6), duration: s.dur, ease: "none", immediateRender: false }, s.at + 0.1);',
    )
    t = t.replace(
        "tl.to(all, { opacity: 1, duration: 0.5 }, 55.9);",
        f"tl.to(all, {{ opacity: 1, duration: 0.5 }}, {dur - 1.2:.2f});",
    )
    t = t.replace(
        '{ opacity: 0, duration: 0.3, ease: "power3.in" }, 56.8);',
        f'{{ opacity: 0, duration: 0.3, ease: "power3.in" }}, {dur - 0.3:.2f});',
    )
    return t


def cards_scene(
    sid: str, label: str, cards: list[tuple[str, str]], times: list[float], dur: float
) -> str:
    """Up to four cards, each a big line and a smaller line, appearing at the given local times."""
    n = len(cards)
    w = 1680 // n - 24
    html = []
    for i, (big, small) in enumerate(cards):
        html.append(
            f'      <div class="card" id="{sid}-card-{i}" style="left:{120 + i * (w + 24)}px; width:{w}px">'
            f'<div class="big">{big}</div><div class="small">{small}</div></div>'
        )
    anim = []
    for i, at in enumerate(times):
        anim.append(
            f'    tl.fromTo("#{sid}-card-{i}", {{ opacity: 0, y: 18 }}, '
            f'{{ opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }}, {at});'
        )
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; font-family: var(--font-sans); color: var(--ink); }}
    #{sid}-label {{ position: absolute; left: 120px; top: 64px; font-weight: 600; font-size: 28px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--live); opacity: 0; }}
    #{sid}-name {{ position: absolute; right: 120px; top: 56px; font-family: var(--font-display); font-weight: 400; font-size: 40px; color: var(--ink); opacity: 0; }}
    .card {{ position: absolute; top: 330px; min-height: 420px; padding: 40px 36px; border: 2px solid var(--border); border-radius: 20px; background: var(--elevated); opacity: 0; }}
    .card .big {{ font-family: var(--font-display); font-weight: 500; font-size: 56px; line-height: 1.08; letter-spacing: -0.01em; color: var(--ink); }}
    .card .big em {{ font-style: normal; color: var(--gold); }}
    .card .small {{ margin-top: 26px; font-size: 30px; line-height: 1.35; color: var(--muted); }}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080">
    <div id="{sid}-block" class="clip" data-start="0" data-duration="{dur}" data-hold>
      <div id="{sid}-label">{esc(label)}</div>
      <div id="{sid}-name">Tallyproof</div>
{chr(10).join(html)}
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#{sid}-label", {{ opacity: 0, y: 6 }}, {{ opacity: 1, y: 0, duration: 0.3 }}, 0);
    tl.fromTo("#{sid}-name", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3 }}, 0);
{chr(10).join(anim)}
    tl.to("#{sid}-block", {{ opacity: 0, duration: 0.3, ease: "power3.in" }}, {dur - 0.3:.2f});
    window.__timelines["{sid}"] = tl;
  </script>
</template>
"""


def where_scene(
    sid: str, label: str, heading: str, items: list[tuple[str, str]], dur: float
) -> str:
    rows = []
    anim = []
    for i, (path, what) in enumerate(items):
        rows.append(
            f'      <div class="row" id="{sid}-row-{i}"><div class="path">{esc(path)}</div><div class="what">{esc(what)}</div></div>'
        )
        anim.append(
            f'    tl.fromTo("#{sid}-row-{i}", {{ opacity: 0, x: -14 }}, {{ opacity: 1, x: 0, duration: 0.35, ease: "power2.out" }}, {0.6 + i * 0.55:.2f});'
        )
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; font-family: var(--font-sans); color: var(--ink); }}
    #{sid}-label {{ position: absolute; left: 120px; top: 64px; font-weight: 600; font-size: 28px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--live); opacity: 0; }}
    #{sid}-name {{ position: absolute; right: 120px; top: 56px; font-family: var(--font-display); font-weight: 400; font-size: 40px; color: var(--ink); opacity: 0; }}
    #{sid}-heading {{ position: absolute; left: 120px; top: 150px; font-family: var(--font-display); font-weight: 400; font-size: 64px; letter-spacing: -0.01em; opacity: 0; }}
    #{sid}-list {{ position: absolute; left: 120px; top: 290px; width: 1680px; display: flex; flex-direction: column; gap: 18px; }}
    .row {{ display: flex; align-items: baseline; gap: 36px; padding: 18px 28px; border: 2px solid var(--border); border-radius: 14px; background: var(--elevated); opacity: 0; }}
    .row .path {{ font-family: var(--font-mono); font-size: 30px; color: var(--live); white-space: nowrap; min-width: 760px; }}
    .row .what {{ font-size: 30px; color: var(--muted); }}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080">
    <div id="{sid}-block" class="clip" data-start="0" data-duration="{dur}" data-hold>
      <div id="{sid}-label">{esc(label)}</div>
      <div id="{sid}-name">Tallyproof</div>
      <div id="{sid}-heading">{esc(heading)}</div>
      <div id="{sid}-list">
{chr(10).join(rows)}
      </div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#{sid}-label", {{ opacity: 0, y: 6 }}, {{ opacity: 1, y: 0, duration: 0.3 }}, 0);
    tl.fromTo("#{sid}-name", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3 }}, 0);
    tl.fromTo("#{sid}-heading", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }}, 0.1);
{chr(10).join(anim)}
    tl.to("#{sid}-block", {{ opacity: 0, duration: 0.3, ease: "power3.in" }}, {dur - 0.3:.2f});
    window.__timelines["{sid}"] = tl;
  </script>
</template>
"""


def pipeline_concept(dur: float) -> str:
    stages = ["Source", "Clean", "Check", "Shape", "Use"]
    boxes = "".join(
        f'      <div class="stage" id="st-{i}" style="left:{200 + i * 330}px"><div class="n">{s}</div></div>\n'
        for i, s in enumerate(stages)
    )
    dots = "".join(f'      <div class="dot" id="dot-{i}"></div>\n' for i in range(6))
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; font-family: var(--font-sans); color: var(--ink); }}
    #c-label {{ position: absolute; left: 120px; top: 64px; font-weight: 600; font-size: 28px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--live); opacity: 0; }}
    #c-name {{ position: absolute; right: 120px; top: 56px; font-family: var(--font-display); font-weight: 400; font-size: 40px; opacity: 0; }}
    #c-head {{ position: absolute; left: 120px; top: 170px; width: 1680px; font-family: var(--font-display); font-weight: 400; font-size: 64px; line-height: 1.1; letter-spacing: -0.01em; opacity: 0; }}
    #rail {{ position: absolute; left: 200px; top: 500px; width: 1520px; height: 3px; background: #2e3344; opacity: 0; }}
    .stage {{ position: absolute; z-index: 2; top: 440px; width: 200px; height: 120px; border: 2px solid var(--border); border-radius: 16px; background: var(--elevated); display: flex; align-items: center; justify-content: center; opacity: 0; }}
    .stage .n {{ font-weight: 700; font-size: 34px; }}
    .dot {{ position: absolute; z-index: 1; top: 491px; left: 200px; width: 20px; height: 20px; border-radius: 50%; background: var(--live); box-shadow: 0 0 18px rgba(34, 211, 238, 0.7); opacity: 0; }}
    .line {{ position: absolute; left: 200px; width: 1520px; font-size: 38px; line-height: 1.3; font-weight: 500; opacity: 0; }}
    .line em {{ font-style: normal; color: var(--gold); }}
    #l-batch {{ top: 660px; }}
    #l-stream {{ top: 740px; }}
    #l-both {{ top: 860px; color: var(--live); }}
  </style>
  <div id="root" data-composition-id="concept" data-width="1920" data-height="1080">
    <div id="c-block" class="clip" data-start="0" data-duration="{dur}" data-hold>
      <div id="c-label">What is a data pipeline</div>
      <div id="c-name">Tallyproof</div>
      <div id="c-head">A chain of steps that moves data from where it is produced to where it is used, cleaning and reshaping it on the way.</div>
      <div id="rail"></div>
{boxes}{dots}
      <div class="line" id="l-batch"><em>Batch:</em> runs on a schedule over large files.</div>
      <div class="line" id="l-stream"><em>Streaming:</em> handles events one at a time, as they arrive.</div>
      <div class="line" id="l-both">Tallyproof has both.</div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#c-label", {{ opacity: 0, y: 6 }}, {{ opacity: 1, y: 0, duration: 0.3 }}, 0);
    tl.fromTo("#c-name", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3 }}, 0);
    tl.fromTo("#c-head", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }}, 0.2);
    tl.fromTo("#rail", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.4 }}, 1.2);
    tl.fromTo(".stage", {{ opacity: 0, y: 12 }}, {{ opacity: 1, y: 0, duration: 0.4, stagger: 0.18, ease: "power2.out" }}, 1.4);
    // dots travel the rail for the rest of the scene, staggered so one is always moving
    for (let i = 0; i < 6; i++) {{
      tl.fromTo("#dot-" + i, {{ opacity: 0, x: 0 }}, {{ opacity: 1, x: 1500, duration: 4.2, ease: "none", repeat: 3, repeatDelay: 0.6, immediateRender: false }}, 2.4 + i * 0.8);
    }}
    tl.fromTo("#l-batch", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }}, 8.6);
    tl.fromTo("#l-stream", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }}, 11.8);
    tl.fromTo("#l-both", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }}, 15.8);
    tl.to("#c-block", {{ opacity: 0, duration: 0.3, ease: "power3.in" }}, {dur - 0.3:.2f});
    window.__timelines["concept"] = tl;
  </script>
</template>
"""


def kafka_concept(dur: float) -> str:
    blocks = "".join(
        f'      <div class="blk" id="blk-{i}" style="left:{560 + i * 92}px"><div class="bn">{i}</div></div>\n'
        for i in range(11)
    )
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; font-family: var(--font-sans); color: var(--ink); }}
    #k-label {{ position: absolute; left: 120px; top: 64px; font-weight: 600; font-size: 28px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--live); opacity: 0; }}
    #k-name {{ position: absolute; right: 120px; top: 56px; font-family: var(--font-display); font-weight: 400; font-size: 40px; opacity: 0; }}
    #k-head {{ position: absolute; left: 120px; top: 170px; width: 1680px; font-family: var(--font-display); font-weight: 400; font-size: 64px; line-height: 1.1; letter-spacing: -0.01em; opacity: 0; }}
    .actor {{ position: absolute; width: 380px; height: 110px; border: 2px solid var(--border); border-radius: 16px; background: var(--elevated); display: flex; flex-direction: column; align-items: center; justify-content: center; opacity: 0; }}
    .actor .n {{ font-weight: 700; font-size: 32px; }}
    .actor .s {{ font-size: 28px; color: var(--muted); margin-top: 4px; }}
    #producer {{ left: 160px; top: 420px; }}
    #consumer-a {{ left: 560px; top: 720px; }}
    #consumer-b {{ left: 1200px; top: 720px; }}
    #topic {{ position: absolute; left: 540px; top: 400px; width: 1060px; height: 150px; border: 2px dashed #3a4052; border-radius: 18px; opacity: 0; }}
    #topic-name {{ position: absolute; left: 560px; top: 356px; font-family: var(--font-mono); font-size: 28px; color: var(--muted); opacity: 0; }}
    .blk {{ position: absolute; top: 430px; width: 80px; height: 90px; border-radius: 10px; background: var(--accent); display: flex; align-items: center; justify-content: center; opacity: 0; }}
    .blk .bn {{ font-family: var(--font-mono); font-size: 28px; color: #0a0b10; font-weight: 700; }}
    .ptr {{ position: absolute; top: 566px; left: 0px; width: 0; height: 0; border-left: 16px solid transparent; border-right: 16px solid transparent; border-bottom: 22px solid var(--live); opacity: 0; }}
    #ptr-a {{ left: 584px; }}
    #ptr-b {{ left: 584px; border-bottom-color: var(--gold); }}
    .ptr-label {{ position: absolute; top: 600px; font-size: 28px; font-family: var(--font-mono); opacity: 0; }}
    #lab-a {{ left: 560px; color: var(--live); }}
    #lab-b {{ left: 1200px; color: var(--gold); }}
    .line {{ position: absolute; left: 120px; width: 1680px; top: 900px; font-size: 38px; line-height: 1.3; font-weight: 500; text-align: center; opacity: 0; }}
    .line em {{ font-style: normal; color: var(--live); }}
  </style>
  <div id="root" data-composition-id="concept" data-width="1920" data-height="1080">
    <div id="k-block" class="clip" data-start="0" data-duration="{dur}" data-hold>
      <div id="k-label">What is Kafka</div>
      <div id="k-name">Tallyproof</div>
      <div id="k-head">A distributed log. Producers append, consumers read in order at their own pace, and nothing is deleted on read.</div>
      <div class="actor" id="producer"><div class="n">Producer</div><div class="s">appends</div></div>
      <div id="topic-name">topic: fin.events.raw.v1</div>
      <div id="topic"></div>
{blocks}
      <div class="ptr" id="ptr-a"></div>
      <div class="ptr" id="ptr-b"></div>
      <div class="ptr-label" id="lab-a">consumer A, offset</div>
      <div class="ptr-label" id="lab-b">consumer B, slower</div>
      <div class="actor" id="consumer-a"><div class="n">Ingestion</div><div class="s">reads, remembers offset</div></div>
      <div class="actor" id="consumer-b"><div class="n">Lake sink</div><div class="s">reads at its own pace</div></div>
      <div class="line" id="l-1">Messages are <em>kept</em>, so the whole stream can be replayed.</div>
      <div class="line" id="l-2">Tallyproof runs <em>Redpanda</em>: Kafka-compatible, one binary, starts on a laptop.</div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#k-label", {{ opacity: 0, y: 6 }}, {{ opacity: 1, y: 0, duration: 0.3 }}, 0);
    tl.fromTo("#k-name", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3 }}, 0);
    tl.fromTo("#k-head", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }}, 0.2);
    tl.fromTo("#producer, #topic, #topic-name", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.4 }}, 1.2);
    // one block appended every 1.3 s
    for (let i = 0; i < 11; i++) {{
      tl.fromTo("#blk-" + i, {{ opacity: 0, x: -30 }}, {{ opacity: 1, x: 0, duration: 0.35, ease: "power2.out", immediateRender: false }}, 1.8 + i * 1.3);
    }}
    tl.fromTo("#consumer-a, #consumer-b, #lab-a, #lab-b", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.4, stagger: 0.1 }}, 5.2);
    tl.fromTo("#ptr-a", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3, immediateRender: false }}, 5.6);
    tl.fromTo("#ptr-b", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3, immediateRender: false }}, 5.6);
    // pointers advance: A keeps up, B trails
    tl.fromTo("#ptr-a", {{ x: 0 }}, {{ x: 92 * 8, duration: 10.4, ease: "steps(8)", immediateRender: false }}, 6.0);
    tl.fromTo("#ptr-b", {{ x: 0 }}, {{ x: 92 * 5, duration: 10.4, ease: "steps(5)", immediateRender: false }}, 6.0);
    tl.fromTo("#l-1", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.4 }}, 11.6);
    tl.to("#l-1", {{ opacity: 0, duration: 0.3 }}, 16.6);
    tl.fromTo("#l-2", {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.4, immediateRender: false }}, 17.0);
    tl.to("#k-block", {{ opacity: 0, duration: 0.3, ease: "power3.in" }}, {dur - 0.3:.2f});
    window.__timelines["concept"] = tl;
  </script>
</template>
"""


# ---------------------------------------------------------------- the two explainers


def spec_pipelines(lens: list[float]) -> dict:
    # scene boundaries from narration lengths
    t_title = round(LEAD + lens[0] + GAP, 2)
    d_concept = round(0.3 + lens[1] + GAP, 2)
    d_map = round(0.5 + lens[2] + GAP + lens[3] + GAP + lens[4] + GAP + lens[5] + GAP, 2)
    d_why = round(0.5 + lens[6] + GAP, 2)
    d_where = round(0.5 + lens[7] + GAP, 2)
    d_outro = round(LEAD + lens[8] + 0.8, 2)
    s_concept = t_title
    s_map = round(s_concept + d_concept, 2)
    s_why = round(s_map + d_map, 2)
    s_where = round(s_why + d_why, 2)
    s_outro = round(s_where + d_where, 2)
    total = round(s_outro + d_outro, 2)
    vo = [LEAD, s_concept + 0.3, s_map + 0.5]
    vo.append(round(vo[2] + lens[2] + GAP, 2))
    vo.append(round(vo[3] + lens[3] + GAP, 2))
    vo.append(round(vo[4] + lens[4] + GAP, 2))
    vo += [s_why + 0.5, s_where + 0.5, s_outro + LEAD]
    m = s_map
    steps = [
        {
            "at": 0.5,
            "dur": round(lens[2], 1),
            "boxes": ["sources", "spark"],
            "wires": ["sources-spark"],
            "cap": "Spark reads about 27 GB of CSV one member at a time, types every column, removes duplicates and personal data. <em>13.3 million rows in, 13.1 million out</em>, as 1.2 GB of Parquet.",
        },
        {
            "at": round(vo[3] - m, 2),
            "dur": round(lens[3], 1),
            "boxes": ["spark"],
            "wires": [],
            "cap": "Deequ checks <em>11 constraints on all 13.1 million rows</em> in 30 seconds. One failure stops the build.",
        },
        {
            "at": round(vo[4] - m, 2),
            "dur": round(lens[4], 1),
            "boxes": ["gold", "replay", "kafka"],
            "wires": ["spark-gold", "gold-replay", "replay-kafka"],
            "cap": "Gold: <em>1,000,000 contract events and 704,400 payments</em> in arrival order, 225 labeled anomalies mixed in. Replayed into Kafka at a controlled pace.",
        },
        {
            "at": round(vo[5] - m, 2),
            "dur": round(lens[5], 1),
            "boxes": ["ingest", "ledger", "checkpointer", "projections", "ws"],
            "wires": [
                "kafka-ingest",
                "ingest-ledger",
                "ledger-checkpointer",
                "ledger-projections",
                "projections-ws",
                "ws-browser",
            ],
            "labels": ["ingest-ledger"],
            "cap": "Streaming: validate, append <em>exactly once</em>, sign, project, push live. The same stream lands in an Iceberg lake, where DuckDB re-runs the rules as SQL.",
        },
    ]
    return {
        "total": total,
        "scenes": [
            ("title", 0, t_title, title_scene("Data pipelines, explained", t_title)),
            ("concept", s_concept, d_concept, pipeline_concept(d_concept)),
            ("map", s_map, d_map, map_scene(steps, d_map, "Where the pipelines run in Tallyproof")),
            (
                "why",
                s_why,
                d_why,
                cards_scene(
                    "why",
                    "Why it is built this way",
                    [
                        (
                            "Report dates were <em>timestamps</em>",
                            "Found only on the real data. Events are now timed by their first report, not their last edit.",
                        ),
                        (
                            "A time zone bug moved every event by <em>4 hours</em>",
                            "Zoned timestamps depended on the machine. Fixed in the history, with a test.",
                        ),
                        (
                            "A million events did not fit in <em>8 GB</em>",
                            "The gold build ran out of memory, so it became a streaming design with flat memory at any size.",
                        ),
                        (
                            "<em>Lake</em> for analytics, <em>ledger</em> for transactions",
                            "The usual split. Control totals keep the stream, the lake, and the gold build in agreement.",
                        ),
                    ],
                    [0.5, 6.0, 11.5, 18.0],
                    d_why,
                ),
            ),
            (
                "where",
                s_where,
                d_where,
                where_scene(
                    "where",
                    "Where to look in the code",
                    "The pipeline in the repository",
                    [
                        (
                            "backend/tallyproof_pipeline/silver.py",
                            "Spark, bronze to silver: types, duplicates, personal data",
                        ),
                        (
                            "backend/tallyproof_pipeline/quality.py",
                            "Deequ constraints and the metrics history",
                        ),
                        (
                            "backend/tallyproof_pipeline/gold.py, overlay.py",
                            "ledger events in arrival order, labeled anomalies",
                        ),
                        ("backend/tallyproof_pipeline/stream.py", "the replay producer into Kafka"),
                        (
                            "backend/tallyproof_pipeline/lake.py, batch_recon.py",
                            "Iceberg sink and the DuckDB reconciliation",
                        ),
                        (
                            "backend/apps/ingestion, ledger, reconciliation",
                            "the streaming side: consumer, append, projections",
                        ),
                    ],
                    d_where,
                ),
            ),
            ("outro", s_outro, d_outro, outro_scene(d_outro)),
        ],
        "vo": vo,
        "marks": [(LEAD - 0.15, "name"), (s_outro + 0.3, "mark")],
    }


def spec_kafka(lens: list[float]) -> dict:
    t_title = round(LEAD + lens[0] + GAP, 2)
    d_concept = round(0.3 + lens[1] + GAP, 2)
    d_map = round(0.5 + lens[2] + GAP + lens[3] + GAP, 2)
    d_num = round(0.5 + lens[4] + GAP, 2)
    d_why = round(0.5 + lens[5] + GAP, 2)
    d_where = round(0.5 + lens[6] + GAP, 2)
    d_outro = round(LEAD + lens[7] + 0.8, 2)
    s_concept = t_title
    s_map = round(s_concept + d_concept, 2)
    s_num = round(s_map + d_map, 2)
    s_why = round(s_num + d_num, 2)
    s_where = round(s_why + d_why, 2)
    s_outro = round(s_where + d_where, 2)
    total = round(s_outro + d_outro, 2)
    vo = [LEAD, s_concept + 0.3, s_map + 0.5]
    vo.append(round(vo[2] + lens[2] + GAP, 2))
    vo += [s_num + 0.5, s_why + 0.5, s_where + 0.5, s_outro + LEAD]
    m = s_map
    steps = [
        {
            "at": 0.5,
            "dur": round(lens[2], 1),
            "boxes": ["replay", "kafka", "sources"],
            "wires": ["replay-kafka"],
            "cap": "Topic <em>fin.events.raw.v1</em>, six partitions, keyed by award so one award stays in order. Producers: the replay tool and the Treasury live connector.",
        },
        {
            "at": round(vo[3] - m, 2),
            "dur": round(lens[3], 1),
            "boxes": ["kafka", "ingest", "ledger"],
            "wires": ["kafka-ingest", "ingest-ledger"],
            "labels": ["ingest-ledger"],
            "cap": "Schema check, Bloom filter, then the ledger's <em>unique key decides</em>. Malformed records go to a dead-letter topic. The offset commits with the append.",
        },
    ]
    return {
        "total": total,
        "scenes": [
            ("title", 0, t_title, title_scene("Kafka, explained", t_title)),
            ("concept", s_concept, d_concept, kafka_concept(d_concept)),
            ("map", s_map, d_map, map_scene(steps, d_map, "Where Kafka sits in Tallyproof")),
            (
                "num",
                s_num,
                d_num,
                cards_scene(
                    "num",
                    "Measured on the laptop",
                    [
                        (
                            "<em>20,000</em> events in 4.0 s",
                            "Published to Kafka using 72 MB, all landing with gap-free leaf indexes.",
                        ),
                        (
                            "About <em>3,000</em> events a second",
                            "Into the ledger, flat from one to three consumers: every append takes the same lock.",
                        ),
                        (
                            "Replay again: <em>nothing</em> appended",
                            "Every duplicate refused by the unique key, and counted.",
                        ),
                    ],
                    [0.5, 5.5, 11.0],
                    d_num,
                ),
            ),
            (
                "why",
                s_why,
                d_why,
                cards_scene(
                    "why",
                    "Why Kafka, and what it is not used for",
                    [
                        (
                            "<em>Decouples</em> producers from a single-writer ledger",
                            "Buffers bursts, and makes every run replayable from the log.",
                        ),
                        (
                            "Derived views read the <em>ledger</em>, not Kafka",
                            "Journal and reconciliation project the signed log in leaf order: exactly-once output, no extra machinery.",
                        ),
                        (
                            "Kafka carries what <em>leaves</em> the database",
                            "Appended events, breaks, and checkpoints, for the live stream and outside consumers.",
                        ),
                    ],
                    [0.5, 9.0, 19.0],
                    d_why,
                ),
            ),
            (
                "where",
                s_where,
                d_where,
                where_scene(
                    "where",
                    "Where to look in the code",
                    "Kafka in the repository",
                    [
                        (
                            "backend/apps/ingestion/consumer.py",
                            "the consumer loop and the staged, idempotent append",
                        ),
                        (
                            "backend/apps/ingestion/dedupe.py, offsets.py",
                            "Bloom filter and the fenced offsets stored with the data",
                        ),
                        (
                            "backend/apps/ingestion/dead_letter.py, schemas.py",
                            "dead-letter topic and the JSON Schema registry",
                        ),
                        ("backend/tallyproof_pipeline/stream.py", "the replay producer"),
                        (
                            "infra/compose.yaml, infra/redpanda",
                            "the Redpanda broker, console, and topic setup",
                        ),
                    ],
                    d_where,
                ),
            ),
            ("outro", s_outro, d_outro, outro_scene(d_outro)),
        ],
        "vo": vo,
        "marks": [(LEAD - 0.15, "name"), (s_outro + 0.3, "mark")],
    }


MUSIC = "assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3"
MUSIC_LEN = 117.36


def music_html(total: float) -> str:
    if total <= MUSIC_LEN:
        return f'      <audio id="music" class="clip" data-start="0" data-duration="{total}" data-track-index="10" data-volume="0.11" data-fade-in="0.5" data-fade-out="1.8" src="{MUSIC}"></audio>\n'
    second = round(MUSIC_LEN - 2.0, 2)
    return (
        f'      <audio id="music" class="clip" data-start="0" data-duration="{MUSIC_LEN}" data-track-index="10" data-volume="0.11" data-fade-in="0.5" data-fade-out="2.0" src="{MUSIC}"></audio>\n'
        f'      <audio id="music-2" class="clip" data-start="{second}" data-duration="{round(total - second, 2)}" data-track-index="14" data-volume="0.11" data-fade-in="2.0" data-fade-out="1.8" src="{MUSIC}"></audio>\n'
    )


def write(spec: dict, comp: Path, lens: list[float]) -> None:
    (comp / "compositions").mkdir(exist_ok=True)
    scene_divs = []
    for sid, start, dur, html in spec["scenes"]:
        (comp / "compositions" / f"{sid}.html").write_text(html)
        scene_divs.append(
            f'      <div id="{sid}" data-composition-id="{sid}" data-composition-src="compositions/{sid}.html" '
            f'data-start="{start}" data-duration="{dur}" data-track-index="1" data-track-kind="graphics" data-width="1920" data-height="1080"></div>'
        )
    vo = []
    for i, (at, dur) in enumerate(zip(spec["vo"], lens, strict=True), 1):
        vo.append(
            f'      <audio id="vo-{i}" class="clip" data-start="{at}" data-duration="{dur:.2f}" data-track-index="3" data-volume="1" src="assets/vo/line-{i}.wav"></audio>'
        )
    marks = []
    for at, kind in spec["marks"]:
        if kind == "name":
            marks.append(
                f'      <audio id="sfx-name" class="clip" data-start="{at:.2f}" data-duration="0.19" data-track-index="11" data-volume="0.5" src="assets/sfx/impact/impactSoft_medium_001.ogg"></audio>'
            )
        else:
            marks.append(
                f'      <audio id="sfx-mark" class="clip" data-start="{at:.2f}" data-duration="1.48" data-track-index="11" data-volume="0.45" src="assets/sfx/impact/impactBell_heavy_000.ogg"></audio>'
            )
    idx = (ARCH / "index.html").read_text()
    head = idx[: idx.index('      <div id="title"')]
    head = head.replace('data-duration="70.1"', f'data-duration="{spec["total"]}"')
    tail = idx[idx.index("    </div>\n    <script>") :]
    total = spec["total"]
    body = (
        "\n".join(scene_divs) + "\n\n"
        "      <!-- Music: Sascha Ende, ende.app (CC BY 4.0). Quiet bed under the narration. -->\n"
        + music_html(total)
        + "      <!-- Narration: Kokoro am_michael, American English, one clip per paragraph -->\n"
        + "\n".join(vo)
        + "\n"
        + "\n".join(marks)
        + "\n"
    )
    (comp / "index.html").write_text(head + body + tail)
    print(f"{comp.parent.name}: {total} s, {len(spec['scenes'])} scenes")
    for sid, start, dur, _ in spec["scenes"]:
        print(f"  {sid:8s} {start:7.2f} +{dur:6.2f}")


def main() -> None:
    which = sys.argv[1]
    comp = composition_dir(which)
    wavs = sorted(
        (comp / "assets" / "vo").glob("line-*.wav"), key=lambda p: int(p.stem.split("-")[1])
    )
    lens = [wav_len(p) for p in wavs]
    spec = spec_pipelines(lens) if which == "pipelines" else spec_kafka(lens)
    write(spec, comp, lens)


if __name__ == "__main__":
    main()
