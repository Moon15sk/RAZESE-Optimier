import tkinter as tk
import tkinter.font as tkfont
import math, random, time

SBG = "#050507"
GOLD, GOLD2 = "#D4AF37", "#F3D77A"
TXT, MUTED = "#EDEDED", "#8A8A98"


def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class Splash(tk.Canvas):
    """Luxury animated loading screen: gold dust, rotating rings, radial progress, shimmering title."""
    TITLE = "RAZESE"

    def __init__(self, master, get_state, on_ready=None, on_done=None, min_time=4.0):
        super().__init__(master, bg=SBG, highlightthickness=0, bd=0)
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.get_state, self.on_ready, self.on_done, self.min_time = get_state, on_ready, on_done, min_time
        self.t0 = self.last = time.time()
        self.disp = 0.0
        self.phase = "run"
        self.t_ready = self.t_out = None
        self.alive = True
        self.readied = False
        self.parts = [{"x": random.random(), "y": random.random(), "v": random.uniform(0.012, 0.05),
                       "s": random.choice((1, 1, 2, 2, 3)), "p": random.uniform(0, 6.28)} for _ in range(70)]
        fam_l, fam = "Segoe UI Light", "Segoe UI"
        self.f_title = tkfont.Font(root=master, family=fam_l, size=62)
        self.f_mono = tkfont.Font(root=master, family=fam_l, size=62)
        self.f_sub = tkfont.Font(root=master, family=fam, size=15)
        self.f_tag = tkfont.Font(root=master, family=fam, size=9, weight="bold")
        self.f_pct = tkfont.Font(root=master, family=fam_l, size=30)
        self.f_msg = tkfont.Font(root=master, family=fam, size=11)
        self.f_lbl = tkfont.Font(root=master, family=fam, size=9, weight="bold")
        self.f_val = tkfont.Font(root=master, family=fam, size=10)
        gap = 18
        ws = [self.f_title.measure(c) for c in self.TITLE]
        self.total = sum(ws) + gap * (len(ws) - 1)
        self.lx, x = [], 0
        for w in ws:
            self.lx.append(x + w / 2 - self.total / 2)
            x += w + gap
        self.after(16, self.frame)

    # ----- lifecycle -----
    def frame(self):
        if not self.alive:
            return
        try:
            self._draw()
        except Exception:
            self._finish()
            return
        if self.alive:
            self.after(16, self.frame)

    def _ready(self):
        if not self.readied:
            self.readied = True
            if self.on_ready:
                try:
                    self.on_ready()
                except Exception:
                    pass

    def _finish(self):
        self.alive = False
        self._ready()
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_done:
            try:
                self.on_done()
            except Exception:
                pass

    # ----- drawing -----
    def _draw(self):
        now = time.time()
        dt = min(0.05, now - self.last)
        self.last = now
        t = now - self.t0
        st = self.get_state()
        w, h = self.winfo_width(), self.winfo_height()
        if w < 100 or h < 100:
            w, h = 1100, 800
        cx, cy = w / 2, h * 0.34

        if self.phase == "run":
            if self.disp < st["target"]:
                self.disp = min(st["target"], self.disp + dt * 0.28)
            if st["done"] and self.disp >= 0.999 and t >= self.min_time:
                self.phase, self.t_ready = "ready", now
                self._ready()
            if t > 30:  # safety net
                self._finish()
                return
        A = 1.0
        if self.phase == "ready" and now - self.t_ready > 1.0:
            self.phase, self.t_out = "out", now
        if self.phase == "out":
            A = max(0.0, 1 - (now - self.t_out) / 0.6)
            if A <= 0:
                self._finish()
                return

        def col(c, a=1.0):
            return lerp(SBG, c, a * A)

        self.delete("all")

        # spotlight glow
        pulse = 0.85 + 0.15 * math.sin(t * 1.6)
        fade = ease(t / 1.5)
        for i in range(14):
            r = 540 * (1 - i / 14)
            k = (i / 14) ** 2 * 0.55 * pulse * fade * A
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=lerp(SBG, "#2a2208", k), outline="")

        # gold dust
        for p in self.parts:
            p["y"] -= p["v"] * dt
            if p["y"] < 0:
                p["y"], p["x"] = 1.0, random.random()
            tw = 0.5 + 0.5 * math.sin(t * 2 + p["p"])
            s, px, py = p["s"], p["x"] * w, p["y"] * h
            self.create_oval(px, py, px + s, py + s, fill=col(GOLD, (0.10 + 0.35 * tw) * fade), outline="")

        # rings
        ra = ease(t / 1.4)
        R = 104
        for rr in (R + 24, R - 34):
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=col("#3a2f10", ra), width=1)
        for k in range(3):
            self.create_arc(cx - R, cy - R, cx + R, cy + R, start=-(t * 80) + k * 120, extent=64 * ra,
                            style="arc", outline=col(GOLD, ra), width=3)
        R2 = R - 16
        for k in range(2):
            self.create_arc(cx - R2, cy - R2, cx + R2, cy + R2, start=(t * 120) + k * 180, extent=36 * ra,
                            style="arc", outline=col(GOLD2, ra * 0.9), width=2)
        ang = t * 1.7
        ox, oy = cx + R * math.cos(ang), cy + R * math.sin(ang)
        self.create_oval(ox - 8, oy - 8, ox + 8, oy + 8, fill=col("#4a3c12", ra), outline="")
        self.create_oval(ox - 3.5, oy - 3.5, ox + 3.5, oy + 3.5, fill=col(GOLD2, ra), outline="")

        # radial progress ticks
        p = 1.0 if self.phase != "run" else self.disp
        n = 72
        for i in range(n):
            a = math.radians(-90 + i * 360 / n)
            frac = i / n
            on = frac < p
            c = lerp(GOLD, GOLD2, frac) if on else "#1c1c26"
            if on and p - frac < 0.03 and self.phase == "run":
                c = "#FFF4D0"
            r1, r2 = R + 34, R + 46 if on else R + 42
            self.create_line(cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a),
                             cy + r2 * math.sin(a), fill=col(c, ra), width=2)

        # ready pulse
        if self.phase in ("ready", "out") and self.t_ready:
            q = min(1.0, (now - self.t_ready) / 1.0)
            rr = R + 46 + q * 280
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=col(GOLD, (1 - q) * 0.8), width=2)

        # monogram
        self.create_text(cx, cy - 4, text="R", font=self.f_mono, fill=col(GOLD, ease((t - 0.3) / 0.8)))

        # title with shimmer
        ty = cy + R + 44 + 78
        u = ((t - 2.4) % 3.0) / 1.1 if t > 2.4 else 9
        sx = cx - self.total / 2 - 100 + u * (self.total + 200)
        for i, ch in enumerate(self.TITLE):
            a = ease((t - (0.5 + 0.13 * i)) / 0.6)
            if a <= 0:
                continue
            x, y = cx + self.lx[i], ty + (1 - a) * 20
            inten = max(0.0, 1 - abs(x - sx) / 80) if u <= 1.0 else 0.0
            base = lerp(GOLD, GOLD2, i / (len(self.TITLE) - 1))
            self.create_text(x, y, text=ch, font=self.f_title, fill=col(lerp(base, "#FFF4D0", inten * 0.85), a))
        lw = 240 * ease((t - 1.4) / 0.7)
        self.create_line(cx - lw / 2, ty + 40, cx + lw / 2, ty + 40, fill=col(GOLD, 0.9), width=1)
        self.create_text(cx, ty + 66, text="O P T I M I Z E R", font=self.f_sub, fill=col(TXT, ease((t - 1.7) / 0.7) * 0.9))
        self.create_text(cx, ty + 92, text="U L T I M A T E   P E R F O R M A N C E", font=self.f_tag,
                         fill=col(MUTED, ease((t - 2.1) / 0.7)))

        # percent + status
        ya = ease((t - 0.9) / 0.6)
        pct = int(p * 100)
        py = h * 0.80
        self.create_text(cx, py, text=f"{pct} %", font=self.f_pct, fill=col(GOLD, ya))
        if self.phase == "run":
            msg = st.get("msg", "")
            wm = self.f_msg.measure(msg)
            self.create_text(cx - 8, py + 38, text=msg, font=self.f_msg, fill=col(MUTED, ya))
            self.create_text(cx - 8 + wm / 2 + 2, py + 38, text="." * (int(t * 2.5) % 4), font=self.f_msg,
                             fill=col(MUTED, ya), anchor="w")
        else:
            self.create_text(cx, py + 38, text="P R I P R A V E N É", font=self.f_lbl, fill=col(GOLD2, 1))

        # discovered components table
        for idx, (ts, label, val) in enumerate(st.get("items", [])[-3:]):
            a = ease((now - ts) / 0.5)
            y = py + 72 + idx * 20
            self.create_text(cx - 10, y, text=label, font=self.f_lbl, fill=col(GOLD, a * 0.9), anchor="e")
            self.create_text(cx + 10, y, text=str(val)[:46], font=self.f_val, fill=col(TXT, a * 0.85), anchor="w")

        self.create_text(cx, h - 22, text="R A Z E S E   •   P R E M I U M   S U I T E", font=self.f_lbl,
                         fill=col("#4a4a58", ease((t - 1.0) / 1.0)))


class Gauge(tk.Canvas):
    """Arc gauge for the live monitor."""

    def __init__(self, master, label, size=190, bg="#13131A"):
        super().__init__(master, width=size, height=size - 10, bg=bg, highlightthickness=0, bd=0)
        self.label, self.size = label, size
        self.set(None, "—", "")

    def set(self, value, text, sub=""):
        self.delete("all")
        s, pad = self.size, 22
        bb = (pad, pad, s - pad, s - pad)
        self.create_arc(*bb, start=225, extent=-270, style="arc", outline="#23232F", width=11)
        if value is not None:
            v = max(0.0, min(100.0, float(value)))
            c = GOLD if v < 75 else ("#E8A33D" if v < 90 else "#E5736B")
            if v > 0.5:
                self.create_arc(*bb, start=225, extent=-270 * v / 100, style="arc", outline=c, width=11)
        self.create_text(s / 2, s / 2 - 6, text=text, font=("Segoe UI Light", 26), fill=TXT)
        self.create_text(s / 2, s / 2 + 22, text=sub, font=("Segoe UI", 9), fill=MUTED)
        self.create_text(s / 2, s - 24, text=self.label, font=("Segoe UI", 10, "bold"), fill=GOLD)


class CoreBars(tk.Canvas):
    """Per-core CPU usage bars."""

    def __init__(self, master, bg="#13131A", height=66):
        super().__init__(master, height=height, bg=bg, highlightthickness=0, bd=0)
        self.hh = height

    def set(self, vals):
        self.delete("all")
        W = max(self.winfo_width(), 300)
        n = max(1, len(vals))
        gap = 4
        bw = (W - gap * (n + 1)) / n
        top = self.hh - 14
        for i, v in enumerate(vals):
            x = gap + i * (bw + gap)
            self.create_rectangle(x, 0, x + bw, top, fill="#1B1B25", outline="")
            hh = top * max(0.0, min(100.0, v)) / 100
            self.create_rectangle(x, top - hh, x + bw, top, fill=lerp(GOLD, GOLD2, v / 100), outline="")
            self.create_text(x + bw / 2, self.hh - 6, text=str(i), font=("Segoe UI", 7), fill=MUTED)
