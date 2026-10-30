import type { SceneSpec, StoryData } from "./types";

// Each scene draws one real mechanism and animates it. Every visual is authored in its
// finished state, so it reads as a still without script or under reduced motion; build()
// tweens the named elements from their starting state on the scene's timeline. Nothing
// loops for decoration: every movement is a step the system takes.

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const q = (root: HTMLElement, name: string) => root.querySelectorAll(`[data-anim="${name}"]`);

function Card({ data, x = 0, y = 0 }: { data: StoryData; x?: number; y?: number }) {
  return (
    <g data-anim="card" transform={`translate(${x} ${y})`}>
      <rect width="300" height="128" rx="12" fill="var(--bg-elevated)" stroke="var(--border)" />
      <text x="18" y="30" fontSize="11" fill="var(--fg-muted)" fontFamily="var(--font-sans)">
        {data.record.agency}
      </text>
      <text x="18" y="52" fontSize="11" fill="var(--fg-muted)" fontFamily="var(--font-mono)">
        {data.record.piid} · {data.record.date}
      </text>
      <text x="18" y="96" fontSize="26" fill="var(--fg)" fontFamily="var(--font-mono)">
        {usd.format(Number(data.record.amount))}
      </text>
      <text x="18" y="116" fontSize="9" fill="var(--fg-muted)" fontFamily="var(--font-mono)">
        {data.record.eventId}
      </text>
    </g>
  );
}

const record: SceneSpec = {
  id: "record",
  number: 1,
  eyebrow: "A record",
  title: "It starts with one real record.",
  caption:
    "A contract obligation from USAspending: the agency, the contract, the amount, the date. Nothing about it is made up, and nothing about it is private.",
  proves: "What follows happens to this exact record, which you can open and verify yourself.",
  visual: (data) => (
    <svg viewBox="0 0 640 220" role="img" aria-label="The record as a card">
      <Card data={data} x={170} y={46} />
    </svg>
  ),
  build: (tl, root) => {
    tl.from(q(root, "card"), { opacity: 0, y: 70, duration: 1 });
  },
};

const stream: SceneSpec = {
  id: "stream",
  number: 2,
  eyebrow: "The stream",
  title: "It joins a stream of records.",
  caption:
    "Records flow through Kafka into the ledger in the order they arrive. A twin delivered twice arrives too, and the ledger refuses it: one idempotency key, one record.",
  proves: "The same record can't be counted twice.",
  visual: (data) => (
    <svg viewBox="0 0 640 220" role="img" aria-label="Records moving along a stream">
      <line x1="0" y1="110" x2="640" y2="110" stroke="var(--border)" strokeDasharray="4 6" />
      <text x="8" y="30" fontSize="10" fill="var(--fg-muted)" fontFamily="var(--font-mono)">
        fin.events.raw.v1
      </text>
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          data-anim="ghost"
          x={40 + i * 150}
          y="86"
          width="110"
          height="48"
          rx="8"
          fill="var(--bg-elevated)"
          stroke="var(--border)"
        />
      ))}
      <g data-anim="ours" transform="translate(540 70)">
        <rect width="120" height="80" rx="10" fill="var(--bg-elevated)" stroke="var(--accent)" />
        <text x="12" y="30" fontSize="10" fill="var(--fg-muted)" fontFamily="var(--font-sans)">
          {data.record.agency.slice(0, 18)}
        </text>
        <text x="12" y="56" fontSize="15" fill="var(--fg)" fontFamily="var(--font-mono)">
          {usd.format(Number(data.record.amount))}
        </text>
      </g>
      <g data-anim="twin" transform="translate(430 140)" opacity="0">
        <rect width="120" height="80" rx="10" fill="var(--bg-elevated)" stroke="var(--warn)" />
        <text x="12" y="30" fontSize="10" fill="var(--fg-muted)" fontFamily="var(--font-sans)">
          the same record, again
        </text>
        <text x="12" y="56" fontSize="15" fill="var(--fg)" fontFamily="var(--font-mono)">
          {usd.format(Number(data.record.amount))}
        </text>
      </g>
      <text data-anim="dropped" x="440" y="206" fontSize="13" fill="var(--warn)" className="script">
        dropped: already in the ledger
      </text>
      <rect
        x="560"
        y="60"
        width="80"
        height="100"
        rx="8"
        fill="var(--bg-sunken)"
        stroke="var(--border)"
      />
      <text
        x="600"
        y="115"
        fontSize="10"
        textAnchor="middle"
        fill="var(--fg-muted)"
        fontFamily="var(--font-sans)"
      >
        ledger
      </text>
    </svg>
  ),
  build: (tl, root) => {
    tl.from(q(root, "ghost"), { x: -520, duration: 2, ease: "none", stagger: 0.1 }, 0);
    tl.from(q(root, "ours"), { x: -130, duration: 2, ease: "none" }, 0.2);
    tl.fromTo(
      q(root, "twin"),
      { x: -130, y: 70, opacity: 0.9 },
      { x: 430, y: 70, opacity: 0.9, duration: 1.6, ease: "none" },
      0.6,
    );
    tl.to(q(root, "twin"), { y: 140, opacity: 0, duration: 0.5 }, 2.2);
    tl.from(q(root, "dropped"), { opacity: 0, duration: 0.4 }, 2.3);
  },
};

const hash: SceneSpec = {
  id: "hash",
  number: 3,
  eyebrow: "The hash",
  title: "Its bytes become one fingerprint.",
  caption:
    "The record is written in canonical form, fields in one fixed order and no spare whitespace, so the same record always gives the same bytes. SHA-256 turns those bytes into a 32-byte leaf.",
  proves: "Change a cent, or a comma, and the leaf changes.",
  visual: (data) => (
    <svg viewBox="0 0 640 220" role="img" aria-label="Canonical bytes collapsing into a hash">
      <g data-anim="bytes">
        <rect
          x="20"
          y="20"
          width="300"
          height="180"
          rx="10"
          fill="var(--bg-sunken)"
          stroke="var(--border)"
        />
        {data.record.canonical
          .split("\n")
          .slice(0, 9)
          .map((line, i) => (
            <text
              key={i}
              x="32"
              y={44 + i * 18}
              fontSize="10"
              fill="var(--fg-muted)"
              fontFamily="var(--font-mono)"
            >
              {line.length > 44 ? `${line.slice(0, 43)}…` : line}
            </text>
          ))}
      </g>
      <path
        data-anim="arrow"
        d="M330 110 H400"
        stroke="var(--accent)"
        strokeWidth="2"
        fill="none"
        strokeDasharray="70"
      />
      <g data-anim="leaf">
        <rect
          x="410"
          y="84"
          width="210"
          height="52"
          rx="10"
          fill="var(--bg-elevated)"
          stroke="var(--accent)"
        />
        <text x="424" y="106" fontSize="9" fill="var(--fg-muted)" fontFamily="var(--font-sans)">
          SHA-256 leaf
        </text>
        <text x="424" y="124" fontSize="12" fill="var(--fg)" fontFamily="var(--font-mono)">
          {data.record.leafHex.slice(0, 16)}…{data.record.leafHex.slice(-6)}
        </text>
      </g>
    </svg>
  ),
  build: (tl, root) => {
    tl.fromTo(
      q(root, "bytes"),
      { scale: 1, opacity: 1, transformOrigin: "330px 110px" },
      { scale: 0.72, opacity: 0.55, transformOrigin: "330px 110px", duration: 1 },
      0,
    );
    tl.from(q(root, "arrow"), { strokeDashoffset: 70, duration: 0.6 }, 0.6);
    tl.from(q(root, "leaf"), { opacity: 0, duration: 0.5 }, 1.1);
  },
};

const tree: SceneSpec = {
  id: "tree",
  number: 4,
  eyebrow: "The tree",
  title: "Leaves pair upward into one root.",
  caption:
    "Every leaf in the log is hashed with its neighbour, and those with theirs, up to a single root. The path from our leaf to the root is a handful of sibling hashes: that is the proof.",
  proves: "One root commits to every record in the log.",
  visual: (data) => {
    const n = data.hops.length;
    const cx = 320;
    const cy = 122;
    const outer = 104;
    const step = Math.min(Math.PI / 5, (Math.PI * 1.7) / Math.max(1, n));
    const ring = (k: number) => outer * Math.sqrt((n - k) / n);
    const pos = (k: number, offset = 0) => {
      const a = k * step + offset;
      return { x: cx + ring(k) * Math.sin(a), y: cy - ring(k) * Math.cos(a) };
    };
    return (
      <svg viewBox="0 0 640 250" role="img" aria-label="The audit path climbing to the root">
        {data.hops.map((h, k) => {
          const a = pos(k);
          const b = k + 1 === n ? { x: cx, y: cy } : pos(k + 1);
          const s = pos(k, h.side === "left" ? -step * 0.45 : step * 0.45);
          return (
            <g key={k} data-anim={`hop-${k}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--accent)" strokeWidth="1.5" />
              <line x1={s.x} y1={s.y} x2={b.x} y2={b.y} stroke="var(--accent)" strokeWidth="1.5" />
              <circle
                cx={a.x}
                cy={a.y}
                r="5"
                fill="var(--bg-elevated)"
                stroke="var(--accent)"
                strokeWidth="2"
              />
              <circle
                cx={s.x}
                cy={s.y}
                r="3.5"
                fill="var(--bg)"
                stroke="var(--accent)"
                strokeWidth="1.5"
                strokeDasharray="2 2"
              />
            </g>
          );
        })}
        <circle
          data-anim="root"
          cx={cx}
          cy={cy}
          r="8"
          fill="var(--bg-elevated)"
          stroke="var(--ok)"
          strokeWidth="2.5"
        />
        <text
          data-anim="rootlabel"
          x={cx}
          y={cy - 16}
          textAnchor="middle"
          fontSize="10"
          fill="var(--fg)"
          fontFamily="var(--font-mono)"
        >
          root {data.rootHex.slice(0, 6)}…{data.rootHex.slice(-4)}
        </text>
        <text x="8" y="240" fontSize="10" fill="var(--fg-muted)" fontFamily="var(--font-mono)">
          {n} sibling hashes · {data.treeSize.toLocaleString("en-US")} leaves
        </text>
      </svg>
    );
  },
  build: (tl, root) => {
    const hops = Array.from(root.querySelectorAll('[data-anim^="hop-"]'));
    hops.forEach((h, k) => tl.from(h, { opacity: k === 0 ? 1 : 0.12, duration: 0.25 }, k * 0.25));
    tl.from(
      q(root, "root"),
      { attr: { stroke: "var(--fg-muted)" }, duration: 0.3 },
      hops.length * 0.25,
    );
    tl.from(q(root, "rootlabel"), { opacity: 0, duration: 0.3 }, hops.length * 0.25);
  },
};

const seal: SceneSpec = {
  id: "seal",
  number: 5,
  eyebrow: "The seal",
  title: "The root is signed.",
  caption:
    "Every few seconds the root is written into a checkpoint note, origin, size, root, and signed with an Ed25519 key. This page trusts exactly one public key, built into it.",
  proves: "Nobody without the key can claim a different history.",
  visual: (data) => (
    <svg viewBox="0 0 640 220" role="img" aria-label="A signed checkpoint note">
      <rect
        x="60"
        y="24"
        width="520"
        height="150"
        rx="10"
        fill="var(--bg-sunken)"
        stroke="var(--border)"
      />
      {data.checkpointNote
        .split("\n")
        .slice(0, 3)
        .map((line, i) => (
          <text
            key={i}
            data-anim="noteline"
            x="80"
            y={54 + i * 22}
            fontSize="12"
            fill="var(--fg)"
            fontFamily="var(--font-mono)"
          >
            {line.length > 60 ? `${line.slice(0, 59)}…` : line}
          </text>
        ))}
      <text
        data-anim="sig"
        x="80"
        y="150"
        fontSize="12"
        fill="var(--accent)"
        fontFamily="var(--font-mono)"
      >
        {(data.checkpointNote.split("\n\n")[1] ?? "").slice(0, 58)}…
      </text>
      <text
        data-anim="key"
        x="80"
        y="200"
        fontSize="11"
        fill="var(--fg-muted)"
        fontFamily="var(--font-sans)"
      >
        signed by the key this page is pinned to
      </text>
    </svg>
  ),
  build: (tl, root) => {
    tl.from(q(root, "noteline"), { opacity: 0, duration: 0.4, stagger: 0.3 }, 0);
    tl.from(q(root, "sig"), { opacity: 0, duration: 0.5 }, 1.2);
    tl.from(q(root, "key"), { opacity: 0, duration: 0.4 }, 1.6);
  },
};

const witness: SceneSpec = {
  id: "witness",
  number: 6,
  eyebrow: "The witness",
  title: "Someone outside writes down the time.",
  caption:
    "The checkpoint's hash is submitted to OpenTimestamps, which anchors it in Bitcoin. Even the holder of the key can't rewrite what was witnessed: a later checkpoint has to be consistent with it.",
  proves: "History can't be quietly replaced after the fact.",
  visual: (data) => (
    <svg viewBox="0 0 640 220" role="img" aria-label="A checkpoint sent to an outside witness">
      <rect
        x="40"
        y="80"
        width="170"
        height="60"
        rx="10"
        fill="var(--bg-elevated)"
        stroke="var(--border)"
      />
      <text x="56" y="106" fontSize="11" fill="var(--fg-muted)" fontFamily="var(--font-sans)">
        checkpoint
      </text>
      <text x="56" y="126" fontSize="12" fill="var(--fg)" fontFamily="var(--font-mono)">
        {data.witnessedSize.toLocaleString("en-US")} leaves
      </text>
      <path
        data-anim="wire"
        d="M215 110 H400"
        stroke="var(--accent-2)"
        strokeWidth="2"
        fill="none"
        strokeDasharray="185"
      />
      <circle data-anim="pulse" cx="400" cy="110" r="4" fill="var(--accent-2)" />
      <rect
        data-anim="stamp"
        x="410"
        y="62"
        width="190"
        height="96"
        rx="10"
        fill="var(--bg-elevated)"
        stroke="var(--accent-2)"
      />
      <text
        data-anim="stamp"
        x="426"
        y="90"
        fontSize="11"
        fill="var(--fg-muted)"
        fontFamily="var(--font-sans)"
      >
        OpenTimestamps
      </text>
      <text
        data-anim="stamp"
        x="426"
        y="112"
        fontSize="12"
        fill="var(--fg)"
        fontFamily="var(--font-mono)"
      >
        anchored in Bitcoin
      </text>
      <text
        data-anim="stamp"
        x="426"
        y="136"
        fontSize="11"
        fill="var(--fg-muted)"
        fontFamily="var(--font-sans)"
      >
        a timestamp nobody can backdate
      </text>
    </svg>
  ),
  build: (tl, root) => {
    tl.from(q(root, "pulse"), { opacity: 0, duration: 0.2 }, 0);
    tl.from(q(root, "pulse"), { attr: { cx: 215 }, duration: 1, ease: "none" }, 0.2);
    tl.from(q(root, "wire"), { strokeDashoffset: 185, duration: 1, ease: "none" }, 0.2);
    tl.from(q(root, "stamp"), { opacity: 0, duration: 0.5, stagger: 0.1 }, 1.2);
  },
};

const question: SceneSpec = {
  id: "question",
  number: 7,
  eyebrow: "The question",
  title: "Ask, and every number comes with its records.",
  caption:
    "The analyst never types a number. It fills in a typed query, the server runs it against the signed log, and the answer's values are bound to the records they came from, each one citable.",
  proves: "An answer can only say what the ledger can prove.",
  visual: (data) => (
    <svg viewBox="0 0 640 220" role="img" aria-label="A question and a cited answer">
      <rect
        x="40"
        y="20"
        width="560"
        height="40"
        rx="20"
        fill="var(--bg-elevated)"
        stroke="var(--border)"
      />
      <text
        data-anim="q"
        x="60"
        y="45"
        fontSize="13"
        fill="var(--fg)"
        fontFamily="var(--font-sans)"
      >
        How much did {data.record.agency} obligate on {data.record.piid}?
      </text>
      <g data-anim="answer">
        <rect
          x="40"
          y="80"
          width="560"
          height="110"
          rx="12"
          fill="var(--bg-elevated)"
          stroke="var(--border)"
        />
        <text x="60" y="112" fontSize="14" fill="var(--fg)" fontFamily="var(--font-sans)">
          {data.record.agency.slice(0, 30)} obligated
        </text>
        <rect
          data-anim="slot"
          x="60"
          y="124"
          width="150"
          height="30"
          rx="6"
          fill="var(--bg-sunken)"
          stroke="var(--accent)"
          strokeWidth="2"
        />
        <text x="72" y="144" fontSize="14" fill="var(--fg)" fontFamily="var(--font-mono)">
          {usd.format(Number(data.record.amount))}
        </text>
        <rect
          data-anim="chip"
          x="220"
          y="126"
          width="36"
          height="26"
          rx="13"
          fill="none"
          stroke="var(--accent)"
        />
        <text
          x="238"
          y="143"
          fontSize="11"
          textAnchor="middle"
          fill="var(--accent)"
          fontFamily="var(--font-mono)"
        >
          c1
        </text>
        <text
          data-anim="cite"
          x="60"
          y="178"
          fontSize="11"
          fill="var(--fg-muted)"
          fontFamily="var(--font-mono)"
        >
          [c1] 1 record · {data.record.eventId} · leaf {data.record.leafIndex} · verify
        </text>
      </g>
    </svg>
  ),
  build: (tl, root) => {
    tl.from(q(root, "answer"), { opacity: 0, duration: 0.6 }, 0.3);
    tl.from(q(root, "slot"), { attr: { "stroke-width": 0 }, duration: 0.4 }, 0.9);
    tl.from(q(root, "chip"), { scale: 0.6, transformOrigin: "238px 139px", duration: 0.4 }, 1.1);
    tl.from(q(root, "cite"), { opacity: 0, duration: 0.4 }, 1.4);
  },
};

export const SCENES: readonly SceneSpec[] = [record, stream, hash, tree, seal, witness, question];
