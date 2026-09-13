"""A companion camera palette for the read-only Factorio spectator.

Run with ``uv run python -m fle.cluster.observer_camera`` after ``fle watch``.
RCON camera updates work while tick_paused; no simulation step is requested.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from factorio_rcon import RCONClient

from fle.cluster.run_envs import RCON_PASSWORD, START_RCON_PORT


def camera_command(action: str, step: int = 16) -> str:
    if action not in {
        "left",
        "right",
        "up",
        "down",
        "home",
        "free",
        "in",
        "out",
        "status",
    }:
        raise ValueError("Unknown camera action")
    if type(step) is not int or not 1 <= step <= 64:
        raise ValueError("Camera step must be 1–64 tiles")
    # Only constant action names and validated integers enter the Lua source.
    return " ".join(
        f"""/sc
local p=game.get_player('fle-observer')
if not p or not p.connected then error('Connect fle-observer with fle watch first') end
if p.controller_type ~= defines.controllers.spectator or p.admin or p.cheat_mode then
    error('Camera requires a non-admin, read-only spectator')
end
local group=p.permission_group
if not group or group.allows_action(defines.input_action.build)
    or group.allows_action(defines.input_action.craft) then
    error('Observer permission policy is missing')
end
local tick,paused,speed=game.tick,game.tick_paused,game.speed
local action='{action}'
local target={{x=p.position.x,y=p.position.y}}
local surface=p.surface
if action=='home' then
    remote.call('fle_runtime','dispatch','__observer_camera_mode','follow')
elseif action=='free' then
    remote.call('fle_runtime','dispatch','__observer_camera_mode','free')
elseif action=='left' then target.x=target.x-{step}
elseif action=='right' then target.x=target.x+{step}
elseif action=='up' then target.y=target.y-{step}
elseif action=='down' then target.y=target.y+{step}
end
if action=='in' then p.zoom=math.min(4,p.zoom*1.25)
elseif action=='out' then p.zoom=math.max(0.15,p.zoom/1.25)
elseif action=='left' or action=='right' or action=='up' or action=='down' then
    if not surface.is_chunk_generated({{math.floor(target.x/32),math.floor(target.y/32)}}) then
        error('Camera destination is outside generated terrain')
    end
    if not p.teleport(target,surface) then error('Camera movement failed') end
    remote.call('fle_runtime','dispatch','__observer_camera_mode','free')
end
local camera=remote.call('fle_runtime','dispatch','__observer_camera_mode')
rcon.print(helpers.table_to_json({{position=p.position,zoom=p.zoom,
    mode=camera.mode,following=camera.following,
    paused=game.tick_paused,tick=game.tick,
    clock_unchanged=game.tick==tick and game.tick_paused==paused and game.speed==speed}}))
""".splitlines()
    )


def move_camera(action: str, step: int = 16, *, instance: int = 0) -> dict:
    command = camera_command(action, step)
    client = RCONClient(
        "127.0.0.1", START_RCON_PORT + instance, RCON_PASSWORD, timeout=3
    )
    try:
        response = client.send_command(command)
    finally:
        client.close()
    try:
        result = json.loads(response)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(str(response).strip() or "No camera response") from exc
    if not result.get("clock_unchanged"):
        raise RuntimeError("Camera clock invariant failed")
    return result


def main() -> None:
    import tkinter as tk
    from collections import deque

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=int, choices=range(33), default=0)
    args = parser.parse_args()
    root = tk.Tk()
    root.title("Factorio observer camera")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.resizable(False, False)
    colors = {
        "rim": "#1c1d1a",
        "panel": "#363831",
        "well": "#242620",
        "button": "#55584b",
        "hover": "#70745f",
        "text": "#e4e1cf",
        "muted": "#b0b29f",
        "amber": "#e8a93e",
        "ink": "#211f18",
    }
    root.configure(bg=colors["rim"])
    root.option_add("*Font", "{Segoe UI} 10")
    frame = tk.Frame(root, bg=colors["panel"], bd=2, relief="raised")
    frame.pack(padx=2, pady=2)
    titlebar = tk.Frame(frame, bg=colors["well"], cursor="fleur")
    titlebar.pack(fill="x")
    title = tk.Label(
        titlebar,
        text="  OBSERVER  /  CAMERA",
        bg=colors["well"],
        fg=colors["amber"],
        font=("Segoe UI", 10, "bold"),
        pady=10,
    )
    title.pack(side="left")
    drag = [0, 0]

    def begin_drag(event):
        drag[:] = [event.x_root - root.winfo_x(), event.y_root - root.winfo_y()]

    def drag_window(event):
        root.geometry(f"+{event.x_root - drag[0]}+{event.y_root - drag[1]}")

    for widget in (titlebar, title):
        widget.bind("<ButtonPress-1>", begin_drag)
        widget.bind("<B1-Motion>", drag_window)

    panel = tk.Frame(frame, bg=colors["panel"], padx=12, pady=12)
    panel.pack(fill="both")
    mode_text = tk.StringVar(value="CONNECTING")
    status = tk.StringVar(value="Looking for the observer…")
    step = tk.IntVar(value=16)
    pool = ThreadPoolExecutor(max_workers=1)
    pending = None
    queue = deque(maxlen=16)
    mode_buttons = {}

    def button(parent, label, command, **kwargs):
        return tk.Button(
            parent,
            text=label,
            command=command,
            bg=colors["button"],
            fg=colors["text"],
            activebackground=colors["hover"],
            activeforeground=colors["text"],
            relief="raised",
            bd=2,
            highlightthickness=0,
            padx=10,
            pady=7,
            cursor="hand2",
            **kwargs,
        )

    def submit(action):
        nonlocal pending
        if pending is not None:
            if action != "status" and len(queue) < queue.maxlen:
                queue.append(action)
            return
        pending = pool.submit(move_camera, action, step.get(), instance=args.instance)
        root.after(30, finish)

    def finish():
        nonlocal pending
        if not pending.done():
            root.after(30, finish)
            return
        try:
            result = pending.result()
            pos = result["position"]
            mode = result["mode"]
            mode_text.set(
                "FREE CAMERA"
                if mode == "free"
                else "FOLLOWING AGENT"
                if result["following"]
                else "WAITING FOR AGENT"
            )
            for name, widget in mode_buttons.items():
                active = mode == name
                widget.configure(
                    bg=colors["amber"] if active else colors["button"],
                    fg=colors["ink"] if active else colors["text"],
                    relief="sunken" if active else "raised",
                )
            state = "Paused" if result["paused"] else "Running"
            status.set(
                f"{state}   ·   Zoom {result['zoom']:.2f}×\n"
                f"Position {pos['x']:.1f}, {pos['y']:.1f}"
            )
        except Exception as exc:
            mode_text.set("CONNECTION / CAMERA ERROR")
            status.set(str(exc)[:200])
            queue.clear()
        pending = None
        if queue:
            submit(queue.popleft())

    modes = tk.Frame(panel, bg=colors["panel"])
    modes.pack(fill="x", pady=(0, 12))
    for name, label, action in (
        ("follow", "Follow agent", "home"),
        ("free", "Free camera", "free"),
    ):
        widget = button(modes, label, lambda a=action: submit(a))
        widget.pack(side="left", expand=True, fill="x", padx=2)
        mode_buttons[name] = widget
    well = tk.Frame(panel, bg=colors["well"], bd=2, relief="sunken", padx=10, pady=9)
    well.pack(fill="x", pady=(0, 10))
    tk.Label(
        well,
        textvariable=mode_text,
        bg=colors["well"],
        fg=colors["amber"],
        font=("Segoe UI", 10, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        well,
        textvariable=status,
        bg=colors["well"],
        fg=colors["text"],
        justify="left",
        anchor="w",
        wraplength=280,
        height=3,
    ).pack(fill="x")
    controls = tk.Frame(panel, bg=colors["panel"])
    controls.pack(fill="x")
    for col in range(3):
        controls.columnconfigure(col, weight=1, uniform="control")
    for label, action, row, col in (
        ("↑", "up", 0, 1),
        ("←", "left", 1, 0),
        ("Home", "home", 1, 1),
        ("→", "right", 1, 2),
        ("↓", "down", 2, 1),
        ("Zoom −", "out", 3, 0),
        ("Zoom +", "in", 3, 2),
    ):
        button(controls, label, lambda a=action: submit(a)).grid(
            row=row, column=col, padx=2, pady=2, sticky="ew"
        )
    tk.Label(
        panel,
        text="PAN DISTANCE",
        bg=colors["panel"],
        fg=colors["muted"],
        font=("Segoe UI", 9, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(12, 5))
    steps = tk.Frame(panel, bg=colors["panel"])
    steps.pack(fill="x")
    for value in (4, 16, 32, 64):
        tk.Radiobutton(
            steps,
            text=str(value),
            variable=step,
            value=value,
            indicatoron=False,
            bg=colors["button"],
            fg=colors["text"],
            selectcolor=colors["well"],
            activebackground=colors["hover"],
            activeforeground=colors["text"],
            bd=2,
            relief="raised",
            pady=5,
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=2)
    tk.Label(
        panel,
        text="WASD / arrows pan • Home follows\n"
        "Shortcuts work while this panel has focus.\nDrag the header to move this panel.",
        bg=colors["panel"],
        fg=colors["muted"],
        justify="left",
        font=("Segoe UI", 9),
    ).pack(anchor="w", pady=(12, 0))
    for key, action in {
        "Left": "left",
        "a": "left",
        "Right": "right",
        "d": "right",
        "Up": "up",
        "w": "up",
        "Down": "down",
        "s": "down",
        "Home": "home",
    }.items():
        root.bind(f"<{key}>", lambda event, a=action: submit(a))

    def close():
        pool.shutdown(wait=False, cancel_futures=True)
        root.destroy()

    button(titlebar, "×", close, font=("Segoe UI", 11, "bold")).pack(side="right")
    root.protocol("WM_DELETE_WINDOW", close)
    root.bind("<Alt-F4>", lambda event: close())

    def refresh():
        submit("status")
        root.after(1500, refresh)

    root.update_idletasks()
    root.geometry(
        f"+{max(0, root.winfo_screenwidth() - root.winfo_reqwidth() - 32)}"
        f"+{max(0, root.winfo_screenheight() - root.winfo_reqheight() - 80)}"
    )
    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
