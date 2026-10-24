"""Sound indicator for SigmaOS-indicator-sound (inspired by indicator-sound).

Principles: pure state transitions (volume/mute/output) with clamping,
fail-fast on unknown outputs, deterministic output listing, thin pactl apply
layer that self_test never runs against a live audio daemon.
"""
import argparse, json, os, subprocess, sys, tempfile

ENGINE = {
    "name": "sigma-sound",
    "summary": "Sound indicator: volume, mute and output switching",
    "language": "python",
    "verbs": ["volume", "output", "mute", "list-outputs"],
    "principles": ["Least Astonishment", "Defensive Programming", "Fail-Fast",
                   "KISS", "Separation of Concerns", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-sound volume 70
volume = 70
$ sigma-sound mute
muted = true
$ sigma-sound output bluez_sink.XX
$ sigma-sound list-outputs
"""

DEFAULT_STORE = os.path.expanduser("~/.config/sigma-sound/state.json")
DEFAULT_OUTPUTS = [
    {"name": "alsa_output.pci.analog-stereo", "description": "Speakers (Built-in Audio)"},
    {"name": "alsa_output.usb-Headset.analog-stereo", "description": "USB Headset"},
    {"name": "bluez_sink.XX_AA.analog-stereo", "description": "Bluetooth Headphones"},
]


class SoundError(ValueError):
    pass


def default_state():
    return {"volume": 50, "muted": False, "active": DEFAULT_OUTPUTS[0]["name"],
            "outputs": [dict(o) for o in DEFAULT_OUTPUTS]}


def validate_state(state):
    for key in ("volume", "muted", "active", "outputs"):
        if key not in state:
            raise SoundError(f"state missing key: {key}")
    if not isinstance(state["outputs"], list) or not state["outputs"]:
        raise SoundError("state needs a non-empty outputs list")
    names = [o.get("name") for o in state["outputs"]]
    if state["active"] not in names:
        raise SoundError(f"active output not in outputs: {state['active']!r}")
    state["volume"] = max(0, min(100, int(state["volume"])))
    state["muted"] = bool(state["muted"])
    return state


def load_state(path):
    if not os.path.exists(path):
        return default_state()
    with open(path, "r", encoding="utf-8") as fh:
        return validate_state(json.load(fh))  # fail-fast on corrupt store


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".sigma-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def set_volume(state, level):
    """Set absolute volume; clamps to 0..100 (least astonishment). Returns level."""
    try:
        v = int(level)
    except (TypeError, ValueError):
        raise SoundError(f"bad volume: {level!r}")
    state["volume"] = max(0, min(100, v))
    return state["volume"]


def adjust_volume(state, delta):
    try:
        d = int(delta)
    except (TypeError, ValueError):
        raise SoundError(f"bad delta: {delta!r}")
    return set_volume(state, state["volume"] + d)


def toggle_mute(state):
    state["muted"] = not state["muted"]
    return state["muted"]


def set_output(state, name):
    """Switch the active output. Fail-fast on unknown names."""
    if name not in [o["name"] for o in state["outputs"]]:
        raise SoundError(f"unknown output: {name} "
                         f"(have: {', '.join(sorted(o['name'] for o in state['outputs']))})")
    state["active"] = name
    return name


def list_outputs(state):
    """Sorted (deterministic) output list; active first is NOT assumed."""
    return sorted(state["outputs"], key=lambda o: o["name"])


def render_pactl(state):
    """Pure renderer: state -> pactl command list."""
    a = state["active"]
    return [f"pactl set-default-sink {a}",
            f"pactl set-sink-volume {a} {state['volume']}%",
            f"pactl set-sink-mute {a} {'1' if state['muted'] else '0'}"]


def apply_state(state, runner=None):
    """Execute layer: run pactl against the real daemon.

    self_test NEVER calls this without an injected (recording) runner.
    """
    cmds = render_pactl(state)
    if runner is None:
        runner = lambda cmd: subprocess.run(cmd.split(), check=True)
    for cmd in cmds:
        runner(cmd)
    return len(cmds)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    p.add_argument("--store", default=DEFAULT_STORE, help="state store (JSON)")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("volume", help="get or set the volume (0..100, clamped)")
    v.add_argument("level", nargs="?", help="absolute level (omit to print current)")
    v.add_argument("--delta", type=int, default=None, help="relative change")
    o = sub.add_parser("output", help="get or set the active output")
    o.add_argument("name", nargs="?", help="output name (omit to print active)")
    m = sub.add_parser("mute", help="toggle or set mute")
    m.add_argument("state", nargs="?", choices=("on", "off", "toggle"), default="toggle")
    sub.add_parser("list-outputs", help="list known outputs (sorted)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        state = load_state(args.store)
        if args.cmd == "volume":
            if args.delta is not None:
                adjust_volume(state, args.delta)
            elif args.level is not None:
                set_volume(state, args.level)
            save_state(args.store, state)
            print(f"volume = {state['volume']}")
        elif args.cmd == "output":
            if args.name:
                set_output(state, args.name)
                save_state(args.store, state)
            print(f"active = {state['active']}")
        elif args.cmd == "mute":
            if args.state == "on":
                state["muted"] = True
            elif args.state == "off":
                state["muted"] = False
            else:
                toggle_mute(state)
            save_state(args.store, state)
            print(f"muted = {'true' if state['muted'] else 'false'}")
        elif args.cmd == "list-outputs":
            for o in list_outputs(state):
                mark = "*" if o["name"] == state["active"] else " "
                print(f"{mark} {o['name']}\t{o['description']}")
        return 0
    except (SoundError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    state = default_state()
    # volume: clamped, fail-fast on garbage
    assert set_volume(state, 70) == 70
    assert set_volume(state, 150) == 100     # clamp high
    assert set_volume(state, -5) == 0        # clamp low
    assert adjust_volume(state, 30) == 30
    try:
        set_volume(state, "loud")
    except SoundError:
        pass
    else:
        raise AssertionError("non-numeric volume not caught")
    # mute toggling
    assert toggle_mute(state) is True
    assert toggle_mute(state) is False
    # output switching: sorted listing, fail-fast on unknown
    assert [o["name"] for o in list_outputs(state)] == sorted(o["name"] for o in DEFAULT_OUTPUTS)
    assert set_output(state, "bluez_sink.XX_AA.analog-stereo") == "bluez_sink.XX_AA.analog-stereo"
    try:
        set_output(state, "hdmi_output.nope")
    except SoundError:
        pass
    else:
        raise AssertionError("unknown output not caught")
    # pactl rendering is pure & deterministic; apply uses an injected sink
    state["volume"], state["muted"] = 42, True
    cmds = render_pactl(state)
    assert cmds == ["pactl set-default-sink bluez_sink.XX_AA.analog-stereo",
                    "pactl set-sink-volume bluez_sink.XX_AA.analog-stereo 42%",
                    "pactl set-sink-mute bluez_sink.XX_AA.analog-stereo 1"]
    seen = []
    assert apply_state(state, runner=seen.append) == 3
    assert seen == cmds
    # persistence round-trip + corrupt-store fail-fast (tempdir only)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state.json")
        save_state(path, state)
        again = load_state(path)
        assert again["volume"] == 42 and again["muted"] is True
        assert load_state(os.path.join(d, "none.json"))["volume"] == 50
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"volume": 10, "muted": false, "active": "ghost", "outputs": []}')
        try:
            load_state(path)
        except SoundError:
            pass
        else:
            raise AssertionError("corrupt store not caught")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
