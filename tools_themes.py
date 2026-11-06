"""مولّد خلفيات المعرض الجاهزة (static/themes/*.svg) — رسوم مسطّحة أصلية على جانبي الصفحة، والوسط خالٍ لبطاقة النموذج.

التشغيل: python tools_themes.py  (يعيد كتابة الملفات؛ قائمة الخلفيات وألوانها في themes.py)
اللوحة 1920×1080 وتُعرض بملء الشاشة (slice)؛ الرسوم في الشريطين x<400 وx>1520 حتى لا تغطيها البطاقة.
"""
import math
import os

from themes import THEMES

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'themes')


def g(x, y, body, r=0, s=1):
    return f'<g transform="translate({x} {y}) rotate({r}) scale({s})">{body}</g>'


# ── عناصر الرسم (كل عنصر حول نقطة الأصل، بحجم 200 تقريباً) ─────────────────

def book_stack(c1, c2, c3):
    return (f'<rect x="-110" y="40" width="220" height="44" rx="6" fill="{c1}"/><rect x="-104" y="48" width="12" height="28" fill="#fff" opacity=".5"/>'
            f'<rect x="-95" y="-6" width="200" height="46" rx="6" fill="{c2}"/><rect x="80" y="2" width="12" height="30" fill="#fff" opacity=".5"/>'
            f'<rect x="-120" y="-52" width="210" height="46" rx="6" fill="{c3}"/><rect x="-112" y="-44" width="160" height="6" fill="#fff" opacity=".45"/>'
            '<rect x="-112" y="-20" width="120" height="6" fill="#fff" opacity=".3"/>')


def pencil(body, tip='#f5d0a9'):
    return (f'<rect x="-14" y="-150" width="28" height="240" fill="{body}"/><rect x="-14" y="-150" width="9" height="240" fill="#fff" opacity=".25"/>'
            '<rect x="-14" y="-178" width="28" height="28" rx="4" fill="#f9a8d4"/><rect x="-14" y="-156" width="28" height="8" fill="#cbd5e1"/>'
            f'<polygon points="-14,90 14,90 0,140" fill="{tip}"/><polygon points="-5,124 5,124 0,140" fill="#1f2937"/>')


def ruler(c):
    ticks = ''.join(f'<rect x="{-150 + i * 20}" y="-22" width="3" height="{18 if i % 2 else 28}" fill="#1f2937" opacity=".55"/>' for i in range(16))
    return f'<rect x="-160" y="-24" width="320" height="56" rx="6" fill="{c}"/>{ticks}'


def clipboard(c, line):
    rows = ''.join(f'<circle cx="-55" cy="{-50 + i * 44}" r="11" fill="none" stroke="{line}" stroke-width="5"/>'
                   f'<rect x="-30" y="{-56 + i * 44}" width="{100 - (i % 2) * 30}" height="12" rx="6" fill="{line}" opacity=".7"/>' for i in range(4))
    tick = f'<path d="M-62 -50 l6 7 l12 -14" stroke="{c}" stroke-width="5" fill="none" stroke-linecap="round"/>'
    return (f'<rect x="-95" y="-120" width="190" height="250" rx="16" fill="{c}"/><rect x="-78" y="-98" width="156" height="212" rx="8" fill="#fff"/>'
            f'<rect x="-40" y="-134" width="80" height="34" rx="10" fill="#334155"/>{rows}{tick}')


def chart_paper(c1, c2):
    return (f'<rect x="-110" y="-140" width="220" height="280" rx="6" fill="#fff"/><rect x="-110" y="-140" width="220" height="280" rx="6" fill="none" stroke="#e2e8f0" stroke-width="3"/>'
            f'<polyline points="-80,-40 -40,-90 0,-60 40,-110 80,-80" fill="none" stroke="{c1}" stroke-width="7" stroke-linejoin="round"/>'
            + ''.join(f'<rect x="{-80 + i * 34}" y="{40 - h}" width="22" height="{h}" fill="{c2}"/>' for i, h in enumerate((40, 70, 55, 95, 75)))
            + '<rect x="-80" y="70" width="160" height="8" rx="4" fill="#cbd5e1"/><rect x="-80" y="92" width="110" height="8" rx="4" fill="#cbd5e1"/>')


def tablet_hand(screen, hand, sleeve):
    lines = ''.join(f'<rect x="-50" y="{-80 + i * 26}" width="{70 + (i * 37) % 30}" height="9" rx="4" fill="{screen}" opacity=".85"/>' for i in range(7))
    return (f'<rect x="-90" y="-130" width="180" height="260" rx="18" fill="#111827"/><rect x="-74" y="-112" width="148" height="224" rx="6" fill="#f8fafc"/>{lines}'
            f'<path d="M-260 70 L-120 30 L-80 60 L-100 100 L-260 140 Z" fill="{sleeve}"/><ellipse cx="-95" cy="62" rx="40" ry="30" fill="{hand}"/>'
            f'<rect x="-80" y="34" width="60" height="18" rx="9" fill="{hand}"/>')


def laptop(screen, body):
    code = ''.join(f'<rect x="{-100 + (i % 3) * 18}" y="{-88 + i * 22}" width="{60 + (i * 41) % 90}" height="9" rx="4" fill="{c}"/>'
                   for i, c in enumerate(('#38bdf8', '#a78bfa', '#f472b6', '#34d399', '#fbbf24', '#38bdf8')))
    return (f'<rect x="-130" y="-110" width="260" height="170" rx="12" fill="{body}"/><rect x="-116" y="-98" width="232" height="146" rx="4" fill="{screen}"/>{code}'
            f'<path d="M-170 60 H170 L150 86 H-150 Z" fill="{body}"/><rect x="-30" y="60" width="60" height="8" rx="4" fill="#94a3b8"/>')


def binary_monitor(c, frame):
    rows = ''.join(f'<text x="-110" y="{-40 + i * 46}" font-family="monospace" font-size="40" fill="#fff" opacity=".85" letter-spacing="4">{t}</text>'
                   for i, t in enumerate(('1001011', '1101001', '0100110')))
    return (f'<rect x="-140" y="-110" width="280" height="190" rx="10" fill="{frame}"/><rect x="-126" y="-96" width="252" height="162" rx="4" fill="{c}"/>{rows}'
            f'<rect x="-20" y="80" width="40" height="50" fill="{frame}"/><rect x="-80" y="126" width="160" height="16" rx="8" fill="{frame}"/>')


def atom(c):
    orb = ''.join(f'<ellipse rx="140" ry="48" fill="none" stroke="{c}" stroke-width="10" transform="rotate({a})"/>' for a in (0, 60, 120))
    return f'{orb}<circle r="26" fill="{c}"/><circle cx="120" cy="-60" r="13" fill="#fff"/><circle cx="-40" cy="118" r="13" fill="#fff"/>'


def flask(glass, liquid):
    return (f'<path d="M-30 -130 H30 V-40 L95 90 Q105 120 75 120 H-75 Q-105 120 -95 90 L-30 -40 Z" fill="{glass}" opacity=".9"/>'
            f'<path d="M-62 30 H62 L95 90 Q105 120 75 120 H-75 Q-105 120 -95 90 Z" fill="{liquid}"/>'
            '<circle cx="-20" cy="70" r="10" fill="#fff" opacity=".7"/><circle cx="25" cy="50" r="7" fill="#fff" opacity=".7"/><circle cx="5" cy="90" r="6" fill="#fff" opacity=".7"/>'
            '<rect x="-38" y="-146" width="76" height="20" rx="6" fill="#e2e8f0"/>')


def molecule(c1, c2):
    pts = [(0, 0), (90, -50), (90, 60), (-80, -70), (-90, 60), (170, -10)]
    bonds = ''.join(f'<line x1="0" y1="0" x2="{x}" y2="{y}" stroke="#fff" stroke-width="8" opacity=".7"/>' for x, y in pts[1:5])
    bonds += '<line x1="90" y1="-50" x2="170" y2="-10" stroke="#fff" stroke-width="8" opacity=".7"/>'
    atoms = ''.join(f'<circle cx="{x}" cy="{y}" r="{34 if i == 0 else 24}" fill="{c1 if i % 2 else c2}"/>' for i, (x, y) in enumerate(pts))
    return bonds + atoms


def leaf(c, vein='#ffffff'):
    return (f'<path d="M0 -150 C90 -90 90 60 0 150 C-90 60 -90 -90 0 -150 Z" fill="{c}"/>'
            f'<path d="M0 -130 V140" stroke="{vein}" stroke-width="5" opacity=".5"/>'
            + ''.join(f'<path d="M0 {y} L{s * 50} {y - 40}" stroke="{vein}" stroke-width="4" opacity=".45"/>' for y in (-60, 0, 60) for s in (-1, 1)))


def plant_pot(pot, l1, l2):
    return (g(-40, -90, leaf(l1), -30, .6) + g(40, -100, leaf(l2), 25, .65) + g(0, -140, leaf(l1), 0, .6)
            + f'<path d="M-80 -10 H80 L62 120 H-62 Z" fill="{pot}"/><rect x="-90" y="-26" width="180" height="30" rx="8" fill="{pot}"/>'
            '<rect x="-90" y="-26" width="180" height="10" rx="5" fill="#fff" opacity=".25"/>')


def sun(c):
    rays = ''.join(f'<rect x="-8" y="-150" width="16" height="44" rx="8" fill="{c}" transform="rotate({a})"/>' for a in range(0, 360, 30))
    return f'{rays}<circle r="88" fill="{c}"/>'


def balloon(c, string='#ffffff'):
    return (f'<path d="M0 120 C -20 170 20 200 0 260" stroke="{string}" stroke-width="3" fill="none" opacity=".8"/>'
            f'<ellipse cx="0" cy="0" rx="78" ry="98" fill="{c}"/><polygon points="-12,96 12,96 0,118" fill="{c}"/>'
            '<ellipse cx="-30" cy="-40" rx="16" ry="28" fill="#fff" opacity=".35"/>')


def confetti(colors, seed, n=26, w=360, h=900):
    out = []
    for i in range(n):
        a = (seed * 9301 + i * 49297) % 233280 / 233280
        b = (seed * 7919 + i * 15485863) % 104729 / 104729
        x, y, c = a * w - w / 2, b * h - h / 2, colors[i % len(colors)]
        out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="14" height="26" rx="4" fill="{c}" transform="rotate({int(a * 360)} {x:.0f} {y:.0f})"/>'
                   if i % 3 else f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" fill="{c}"/>')
    return ''.join(out)


def star(c, r=60):
    pts = ' '.join(f'{(r if i % 2 == 0 else r * .45) * math.sin(i * math.pi / 5):.1f},{-(r if i % 2 == 0 else r * .45) * math.cos(i * math.pi / 5):.1f}'
                   for i in range(10))
    return f'<polygon points="{pts}" fill="{c}" stroke-linejoin="round"/>'


def gift(box, ribbon):
    return (f'<rect x="-90" y="-40" width="180" height="140" rx="8" fill="{box}"/><rect x="-100" y="-70" width="200" height="40" rx="8" fill="{box}"/>'
            f'<rect x="-14" y="-70" width="28" height="170" fill="{ribbon}"/><path d="M0 -70 C-60 -140 -100 -80 0 -70 C100 -80 60 -140 0 -70" fill="none" stroke="{ribbon}" stroke-width="14"/>')


def palette(c, dots):
    d = ''.join(f'<circle cx="{x}" cy="{y}" r="24" fill="{col}"/>' for (x, y), col in zip(((-70, -40), (-20, -80), (45, -70), (85, -15), (-80, 30)), dots))
    return (f'<path d="M0 -130 C120 -130 170 -40 150 30 C135 80 80 60 60 90 C40 125 70 150 20 150 C-100 150 -160 70 -150 -20 C-140 -90 -80 -130 0 -130 Z" fill="{c}"/>'
            f'{d}<circle cx="20" cy="70" r="28" fill="#00000022"/>')


def brush(handle, tip):
    return (f'<rect x="-11" y="-170" width="22" height="210" rx="10" fill="{handle}"/><rect x="-14" y="30" width="28" height="36" fill="#cbd5e1"/>'
            f'<path d="M-14 66 H14 Q16 120 0 150 Q-16 120 -14 66 Z" fill="{tip}"/>')


def trophy(c, base):
    return (f'<path d="M-80 -120 H80 V-40 Q80 40 0 50 Q-80 40 -80 -40 Z" fill="{c}"/>'
            f'<path d="M-80 -100 Q-140 -100 -130 -50 Q-120 0 -70 -10" fill="none" stroke="{c}" stroke-width="16"/>'
            f'<path d="M80 -100 Q140 -100 130 -50 Q120 0 70 -10" fill="none" stroke="{c}" stroke-width="16"/>'
            f'<rect x="-16" y="48" width="32" height="50" fill="{c}"/><rect x="-70" y="96" width="140" height="36" rx="6" fill="{base}"/>'
            '<rect x="-55" y="-105" width="18" height="90" rx="9" fill="#fff" opacity=".35"/>')


def ball(c1, c2):
    pent = ''.join(f'<polygon points="{" ".join(f"{cx + 22 * math.sin(k * 1.2566):.0f},{cy - 22 * math.cos(k * 1.2566):.0f}" for k in range(5))}" fill="{c2}"/>'
                   for cx, cy in ((0, 0), (-62, -40), (62, -40), (-40, 60), (40, 60)))
    return f'<circle r="100" fill="{c1}"/>{pent}<circle r="100" fill="none" stroke="{c2}" stroke-width="5"/>'


def medal(ribbon, c):
    return (f'<polygon points="-50,-150 -10,-150 20,-40 -20,-40" fill="{ribbon}"/><polygon points="50,-150 10,-150 -20,-40 20,-40" fill="{ribbon}" opacity=".8"/>'
            f'<circle cy="20" r="70" fill="{c}"/><circle cy="20" r="50" fill="none" stroke="#fff" stroke-width="6" opacity=".6"/>{g(0, 20, star("#ffffff", 30))}')


def grad_cap(c, tassel):
    return (f'<polygon points="0,-90 190,-20 0,50 -190,-20" fill="{c}"/><path d="M-110 10 V80 Q0 130 110 80 V10 L0 50 Z" fill="{c}"/>'
            f'<polygon points="0,-90 190,-20 0,50 -190,-20" fill="#fff" opacity=".12"/><path d="M0 -20 L150 30 V110" stroke="{tassel}" stroke-width="6" fill="none"/>'
            f'<rect x="138" y="105" width="24" height="44" rx="6" fill="{tassel}"/>')


def diploma(paper, ribbon):
    return (f'<rect x="-150" y="-50" width="300" height="100" rx="50" fill="{paper}"/><ellipse cx="-150" cy="0" rx="22" ry="50" fill="#e7d9b8"/>'
            f'<rect x="-20" y="-50" width="40" height="100" fill="{ribbon}"/><path d="M-10 50 L-30 120 L0 100 L30 120 L10 50" fill="{ribbon}"/>')


def bubble(c, flip=False, dots=True):
    tail = '<polygon points="60,50 110,110 20,62" fill="{}"/>'.format(c) if flip else '<polygon points="-60,50 -110,110 -20,62" fill="{}"/>'.format(c)
    d = '<circle cx="-45" cy="0" r="14" fill="#fff"/><circle cx="0" cy="0" r="14" fill="#fff"/><circle cx="45" cy="0" r="14" fill="#fff"/>' if dots else \
        '<rect x="-80" y="-24" width="160" height="12" rx="6" fill="#fff" opacity=".85"/><rect x="-80" y="6" width="110" height="12" rx="6" fill="#fff" opacity=".85"/>'
    return f'<rect x="-130" y="-70" width="260" height="140" rx="40" fill="{c}"/>{tail}{d}'


def bulb(c):
    return (f'<circle cy="-40" r="90" fill="{c}"/><path d="M-50 20 Q-40 60 -36 90 H36 Q40 60 50 20 Z" fill="{c}"/>'
            '<rect x="-38" y="92" width="76" height="20" rx="6" fill="#94a3b8"/><rect x="-32" y="114" width="64" height="18" rx="6" fill="#64748b"/>'
            '<path d="M-20 -30 Q0 -70 20 -30" stroke="#fff" stroke-width="7" fill="none" opacity=".7"/><ellipse cx="-40" cy="-80" rx="16" ry="26" fill="#fff" opacity=".35"/>')


def rating(c, off):
    return ''.join(g(-150 + i * 75, 0, star(c if i < 4 else off, 34)) for i in range(5))


def heart(c):
    return f'<path d="M0 60 C-110 -10 -80 -110 0 -60 C80 -110 110 -10 0 60 Z" fill="{c}"/>'


def calendar(c):
    cells = ''.join(f'<rect x="{-90 + (i % 5) * 38}" y="{-30 + (i // 5) * 34}" width="26" height="22" rx="4" fill="{c if i == 7 else "#cbd5e1"}"/>' for i in range(15))
    return (f'<rect x="-110" y="-110" width="220" height="210" rx="16" fill="#fff"/><rect x="-110" y="-110" width="220" height="60" rx="16" fill="{c}"/>'
            f'<rect x="-110" y="-70" width="220" height="20" fill="{c}"/><rect x="-70" y="-130" width="16" height="44" rx="8" fill="#334155"/><rect x="54" y="-130" width="16" height="44" rx="8" fill="#334155"/>{cells}')


def islamic_star(c1, c2, r=120):
    sq = f'<rect x="{-r * .7:.0f}" y="{-r * .7:.0f}" width="{r * 1.4:.0f}" height="{r * 1.4:.0f}" fill="{c1}"/>'
    return (sq + f'<g transform="rotate(45)">{sq}</g>' + f'<circle r="{r * .55:.0f}" fill="{c2}"/>'
            + f'<rect x="{-r * .32:.0f}" y="{-r * .32:.0f}" width="{r * .64:.0f}" height="{r * .64:.0f}" fill="{c1}" transform="rotate(45)"/>')


def waves(colors):
    out = []
    for i, c in enumerate(colors):
        y = 760 + i * 70
        out.append(f'<path d="M0 {y} C 320 {y - 90} 640 {y + 90} 960 {y} S 1600 {y - 90} 1920 {y} V1080 H0 Z" fill="{c}"/>')
    return ''.join(out)


def blob(x, y, r, c, op=.12):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}" opacity="{op}"/>'


# ── تركيب كل خلفية ───────────────────────────────────────────────────────────

def compose(key):
    t = THEMES[key]
    bg, a = t['bg'], t['accent']
    deco = blob(160, 160, 300, '#ffffff', .07) + blob(1800, 960, 340, '#ffffff', .06)
    if key == 'classroom':
        art = (g(200, 260, book_stack('#f59e0b', '#ef4444', '#22c55e'), -6) + g(110, 700, pencil('#facc15'), 28) + g(300, 900, ruler('#fde68a'), -14)
               + g(1720, 230, clipboard('#f97316', '#94a3b8'), 10) + g(1700, 820, book_stack('#38bdf8', '#a78bfa', '#f472b6'), 4)
               + g(1840, 560, pencil('#fb7185'), -20, .8))
    elif key == 'science':
        art = (g(210, 250, atom('#5eead4'), 0, .95) + g(150, 760, flask('#e0f2fe', '#a3e635'), -10) + g(330, 560, molecule('#fde047', '#f472b6'), 0, .6)
               + g(1720, 260, flask('#e0f2fe', '#f472b6'), 12, .9) + g(1690, 800, molecule('#38bdf8', '#fde047'), -10, .9)
               + g(1860, 560, atom('#fde047'), 30, .5))
    elif key == 'technology':
        art = (g(250, 260, tablet_hand('#7c3aed', '#f2c094', '#2563eb'), -12) + g(190, 820, chart_paper('#7c3aed', '#a78bfa'), -8)
               + g(1700, 790, binary_monitor('#7c3aed', '#4c1d95'), 0, .95) + g(1730, 300, laptop('#0f172a', '#cbd5e1'), 8, .85)
               + g(1860, 560, leaf('#2f855a'), 45, .45))
    elif key == 'nature':
        art = (g(170, 220, sun('#fde047'), 0, .8) + g(200, 800, plant_pot('#c2410c', '#22c55e', '#16a34a'), -4, 1.05) + g(360, 470, leaf('#4ade80'), -35, .55)
               + g(1720, 260, leaf('#86efac'), 30, .9) + g(1830, 420, leaf('#22c55e'), -20, .6) + g(1700, 820, plant_pot('#0f766e', '#4ade80', '#bbf7d0'), 6, .95))
    elif key == 'celebration':
        art = (g(200, 0, confetti(['#fde047', '#f472b6', '#38bdf8', '#a3e635', '#fff'], 3), 0) + g(1720, 0, confetti(['#fde047', '#fff', '#38bdf8', '#fb923c'], 7), 0)
               + g(190, 300, balloon('#fde047'), -8) + g(320, 380, balloon('#38bdf8'), 10, .8) + g(1700, 320, balloon('#f9a8d4'), 6)
               + g(1830, 260, balloon('#a3e635'), -10, .75) + g(220, 860, gift('#fb923c', '#fff7ed'), -6, .9) + g(1720, 860, star('#fde047', 70), 15)
               + g(1850, 760, star('#ffffff', 34), -10))
        art = art.replace('translate(200 0)', 'translate(200 540)').replace('translate(1720 0)', 'translate(1720 540)')
    elif key == 'arts':
        art = (g(220, 300, palette('#fef3c7', ['#ef4444', '#3b82f6', '#22c55e', '#eab308', '#a855f7']), -12) + g(120, 760, brush('#7c2d12', '#2563eb'), 25)
               + g(310, 820, brush('#1e3a8a', '#ef4444'), -15, .9) + g(1720, 280, brush('#b45309', '#22c55e'), -30, .95)
               + g(1700, 780, palette('#fff7ed', ['#f97316', '#0ea5e9', '#e11d48', '#84cc16', '#facc15']), 18, .9)
               + blob(1850, 520, 40, '#3b82f6', .9) + blob(1600, 600, 26, '#ef4444', .9) + blob(380, 560, 30, '#eab308', .95))
    elif key == 'sports':
        art = (g(200, 260, trophy('#facc15', '#a16207'), -6) + g(180, 800, ball('#ffffff', '#1f2937'), 0, .95) + g(360, 560, medal('#ef4444', '#f59e0b'), 12, .6)
               + g(1720, 300, medal('#2563eb', '#e5e7eb'), -8, .95) + g(1720, 820, ball('#f97316', '#7c2d12'), 20, .9) + g(1860, 560, star('#facc15', 40), 0))
    elif key == 'graduation':
        art = (g(240, 260, grad_cap('#0f172a', '#facc15'), -10) + g(220, 820, diploma('#fef9c3', '#dc2626'), -14) + g(380, 560, star('#facc15', 34), 0)
               + g(1700, 300, diploma('#fef9c3', '#2563eb'), 16, .9) + g(1700, 800, grad_cap('#1e293b', '#fbbf24'), 8, .85)
               + g(1860, 560, star('#ffffff', 26), 12) + g(1560, 120, star('#facc15', 22), 0) + g(120, 560, star('#ffffff', 22), 0))
    elif key == 'feedback':
        art = (g(220, 240, bubble('#f472b6'), -4) + g(190, 560, rating('#facc15', '#ffffff55'), -6, .9) + g(220, 860, clipboard('#22d3ee', '#94a3b8'), -10, .9)
               + g(1720, 260, bulb('#fde047'), 10, .9) + g(1700, 600, bubble('#38bdf8', True, False), 6, .9) + g(1760, 900, heart('#fb7185'), -12, .9))
    elif key == 'heritage':
        tiles = ''.join(g(x, y, islamic_star('#d6b98c', '#f8efe0', 70), 0) for x in (90, 290) for y in (120, 360, 600, 840, 1080))
        tiles += ''.join(g(x, y, islamic_star('#d6b98c', '#f8efe0', 70), 0) for x in (1630, 1830) for y in (120, 360, 600, 840, 1080))
        tiles += ''.join(g(x, y, islamic_star('#b98b4e', '#d6b98c', 34), 0) for x in (190, 1730) for y in (240, 480, 720, 960))
        art = tiles
        deco = ''
    elif key == 'calm':
        art = (waves(['#bfdbfe', '#93c5fd', '#60a5fa']) + g(220, 230, calendar('#2563eb'), -8, .9) + g(1700, 260, bulb('#fde68a'), 8, .8)
               + g(1840, 520, star('#ffffff', 26), 0) + g(150, 520, star('#ffffff', 20), 0))
    elif key == 'community':
        art = (g(220, 260, bubble('#fb923c'), -6) + g(320, 470, heart('#f43f5e'), 10, .7) + g(200, 820, calendar('#0d9488'), -8, .95)
               + g(1720, 260, heart('#fb7185'), -8) + g(1700, 600, bubble('#14b8a6', True), 4, .85) + g(1740, 880, star('#fbbf24', 54), 10))
    else:
        raise KeyError(key)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">'
            f'<rect width="1920" height="1080" fill="{bg}"/>{deco}{art}</svg>')


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for k in THEMES:
        with open(os.path.join(OUT, f'{k}.svg'), 'w', encoding='utf-8') as fh:
            fh.write(compose(k))
        print(k)
