"""Monkey patches that make macOS trackpad scrolling behave inside CTkScrollableFrame.

CustomTkinter's CTkScrollableFrame implements scrolling by binding <MouseWheel>
on Windows and <Button-4>/<Button-5> on X11. On macOS the system delivers
<MouseWheel> events with delta values that the default handler miscalculates
(off-by-one issues, jitter, sticky scroll position). These patches replace
the relevant private methods with versions that:

1. Normalize macOS trackpad delta to a fraction of the visible canvas height.
2. Fall back to the original implementation when the master is not a Canvas
   (CustomTkinter's internal check is unreliable on macOS).
3. Bridge Tk 9's <TouchpadScroll> events (separate from <MouseWheel>) into
   the same handler so high-frequency trackpad gestures don't get dropped.
4. Preserve in-Textbox scrolling when the cursor is over a Text widget that
   itself can scroll (log panel inside a scrollable frame).

The patches must be applied before any CTkScrollableFrame is constructed --
the main window does that as its first step.
"""

import sys


def apply_scroll_patches(*, scroll_delta_scale, min_fraction_step,
                          max_fraction_step, logger):
    """Install robust_* overrides on CustomTkinter's CTkScrollableFrame.

    Idempotent: calling twice is a no-op.

    Args:
        scroll_delta_scale: macOS trackpad delta multiplier (typically 1.35).
        min_fraction_step: smallest allowed scroll fraction per event
            (avoids dead/sticky zones when delta is near zero).
        max_fraction_step: largest allowed scroll fraction per event
            (prevents jumpy fast-flick gestures).
        logger: a logging.Logger for diagnostics. Failure paths log via this
            instead of `print` so callers can route messages appropriately.
    """
    try:
        import customtkinter as ctk
    except Exception:
        raise RuntimeError('Tkinter/CustomTkinter is required for GUI mode')

    def robust_check_if_master_is_canvas(self, widget):
        try:
            if not widget:
                return False
            if isinstance(widget, str):
                try:
                    widget = self.nametowidget(widget)
                except Exception:
                    canvas_path = str(self._parent_canvas)
                    frame_path = str(self._parent_frame)
                    scrollbar_path = str(self._scrollbar)
                    if (
                        widget == canvas_path or widget.startswith(canvas_path + ".")
                        or widget == frame_path or widget.startswith(frame_path + ".")
                        or widget == scrollbar_path or widget.startswith(scrollbar_path + ".")
                    ):
                        return True
                    return False

            if widget in (self._parent_canvas, self._parent_frame, self._scrollbar, self):
                return True

            if hasattr(widget, "master") and widget.master is not None:
                return robust_check_if_master_is_canvas(self, widget.master)
            elif hasattr(widget, "winfo_parent"):
                try:
                    parent_name = widget.winfo_parent()
                    if parent_name:
                        parent = self.nametowidget(parent_name)
                        return robust_check_if_master_is_canvas(self, parent)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Error in robust_check_if_master_is_canvas: {e}")
        return False

    def robust_widget_is_inside_scrollable(self, widget):
        """Return True when a widget belongs to this scrollable frame tree."""
        try:
            if not widget:
                return False
            if isinstance(widget, str):
                try:
                    widget = self.nametowidget(widget)
                except Exception:
                    return False

            current = widget
            while current is not None:
                if current in (self._parent_canvas, self._parent_frame, self._scrollbar, self):
                    return True
                if hasattr(current, "master"):
                    current = current.master
                else:
                    current = None
        except Exception:
            return False
        return False

    def robust_mouse_wheel_all(self, event):
        try:
            event_widget = getattr(event, "widget", None)
            pointer_widget = None
            in_canvas = self.check_if_master_is_canvas(event_widget)
            if not in_canvas:
                pointer_widget = self.winfo_containing(
                    getattr(event, "x_root", 0),
                    getattr(event, "y_root", 0),
                )
                in_canvas = robust_widget_is_inside_scrollable(self, pointer_widget)

            delta = int(getattr(event, "delta", 0) or 0)
            if delta == 0:
                button_num = getattr(event, "num", None)
                if button_num == 4:
                    delta = 1
                elif button_num == 5:
                    delta = -1
            if delta == 0:
                return

            shift_pressed = bool(
                getattr(self, "_shift_pressed", False)
                or (getattr(event, "state", 0) & 0x0001)
            )

            if in_canvas:
                curr = event_widget or pointer_widget
                try:
                    if isinstance(curr, str):
                        curr = self.nametowidget(curr)
                except Exception:
                    curr = None

                text_widget = None
                temp = curr
                while temp:
                    if temp.__class__.__name__ in ('Text', 'CTkTextbox') or isinstance(temp, ctk.CTkTextbox):
                        text_widget = temp
                        break
                    if hasattr(temp, 'winfo_parent'):
                        try:
                            parent_name = temp.winfo_parent()
                            temp = self.nametowidget(parent_name) if parent_name else None
                        except Exception:
                            temp = None
                    else:
                        temp = None

                if text_widget is not None and not bool(getattr(text_widget, "_prefer_parent_scroll", False)):
                    try:
                        view = text_widget.xview() if shift_pressed else text_widget.yview()
                        first, last = float(view[0]), float(view[1])
                    except Exception:
                        first, last = 0.0, 1.0

                    can_scroll_here = not (first <= 0.0 and last >= 1.0)
                    if can_scroll_here:
                        if delta > 0 and first <= 0.0:
                            can_scroll_here = False
                        elif delta < 0 and last >= 1.0:
                            can_scroll_here = False
                    if can_scroll_here:
                        return

                if sys.platform == 'darwin':
                    raw_delta = float(delta)
                    if abs(raw_delta) >= 60.0:
                        raw_delta = raw_delta / 120.0
                    canvas = self._parent_canvas
                    span_getter = canvas.xview if shift_pressed else canvas.yview
                    mover = canvas.xview_moveto if shift_pressed else canvas.yview_moveto
                    axis_idx = 0 if shift_pressed else 1
                    try:
                        region = canvas.cget("scrollregion")
                        if region:
                            p = [float(v) for v in str(region).split()]
                            total_extent = abs((p[2] - p[0]) if axis_idx == 0 else (p[3] - p[1]))
                        else:
                            total_extent = 0.0
                    except Exception:
                        total_extent = 0.0

                    start, end = span_getter()
                    if total_extent > 0:
                        step = (-raw_delta * scroll_delta_scale) / total_extent
                    else:
                        step = (-raw_delta) * 0.0015

                    if abs(step) < min_fraction_step:
                        step = min_fraction_step if step >= 0 else -min_fraction_step
                    if step > max_fraction_step:
                        step = max_fraction_step
                    elif step < -max_fraction_step:
                        step = -max_fraction_step

                    viewport_span = max(0.0, end - start)
                    max_start = max(0.0, 1.0 - viewport_span)
                    new_start = start + step
                    if new_start < 0.0:
                        new_start = 0.0
                    elif new_start > max_start:
                        new_start = max_start
                    mover(new_start)
                    return
                else:
                    scroll_units = int(-1 * (delta / 120) * 3)

                if scroll_units != 0:
                    if shift_pressed and self._parent_canvas.xview() != (0.0, 1.0):
                        self._parent_canvas.xview_scroll(int(scroll_units), "units")
                    elif self._parent_canvas.yview() != (0.0, 1.0):
                        self._parent_canvas.yview_scroll(int(scroll_units), "units")
        except Exception:
            logger.exception("Error in robust_mouse_wheel_all")

    def install_touchpad_scroll_bridge(root_widget, scrollable_frame):
        """Bridge Tk9 <TouchpadScroll> events to the existing MouseWheel handler."""
        if sys.platform != "darwin":
            return
        if getattr(root_widget, "_touchpad_scroll_bridge_installed", False):
            return

        try:
            root_widget.tk.call("bind", "all", "<TouchpadScroll>")
        except Exception:
            return

        def _parse_precise_deltas(packed_delta):
            try:
                parsed = root_widget.tk.call("tk::PreciseScrollDeltas", packed_delta)
                if isinstance(parsed, (tuple, list)) and len(parsed) >= 2:
                    dx_raw, dy_raw = parsed[0], parsed[1]
                else:
                    parts = str(parsed).split()
                    dx_raw = parts[0] if parts else 0
                    dy_raw = parts[1] if len(parts) > 1 else 0
                return float(dx_raw), float(dy_raw)
            except Exception:
                return 0.0, 0.0

        def _touchpad_bridge(widget_name, packed_delta, state_raw, x_root_raw, y_root_raw):
            try:
                delta_x, delta_y = _parse_precise_deltas(packed_delta)
                if delta_x == 0 and delta_y == 0:
                    return ""

                try:
                    state = int(float(state_raw))
                except Exception:
                    state = 0
                try:
                    x_root = int(float(x_root_raw))
                    y_root = int(float(y_root_raw))
                except Exception:
                    x_root = 0
                    y_root = 0

                event_widget = None
                if widget_name:
                    try:
                        event_widget = root_widget.nametowidget(widget_name)
                    except Exception:
                        event_widget = None
                if event_widget is None and (x_root or y_root):
                    try:
                        event_widget = root_widget.winfo_containing(x_root, y_root)
                    except Exception:
                        event_widget = None
                if event_widget is None:
                    event_widget = scrollable_frame

                if not robust_widget_is_inside_scrollable(scrollable_frame, event_widget):
                    return ""

                class SyntheticWheelEvent:
                    __slots__ = ("widget", "delta", "state", "x_root", "y_root", "num")

                    def __init__(self, widget, delta, state, x_root, y_root):
                        self.widget = widget
                        self.delta = int(delta)
                        self.state = state
                        self.x_root = x_root
                        self.y_root = y_root
                        self.num = None

                if abs(delta_y) > 0:
                    ev_y = SyntheticWheelEvent(event_widget, int(round(delta_y)), state, x_root, y_root)
                    robust_mouse_wheel_all(scrollable_frame, ev_y)

                if abs(delta_x) > 0:
                    ev_x = SyntheticWheelEvent(
                        event_widget, int(round(delta_x)),
                        (state | 0x0001), x_root, y_root,
                    )
                    robust_mouse_wheel_all(scrollable_frame, ev_x)
            except Exception:
                logger.exception("Error in touchpad bridge callback")
            return ""

        bridge_cmd = root_widget.register(_touchpad_bridge)
        try:
            root_widget.tk.call(
                "bind",
                "all",
                "<TouchpadScroll>",
                f"+{bridge_cmd} %W %D %s %X %Y",
            )
            root_widget._touchpad_scroll_bridge_installed = True
        except Exception:
            logger.info("TouchpadScroll bridge unavailable in this Tk build; falling back to MouseWheel only.")

    ctk.CTkScrollableFrame.check_if_master_is_canvas = robust_check_if_master_is_canvas
    ctk.CTkScrollableFrame._mouse_wheel_all = robust_mouse_wheel_all

    return install_touchpad_scroll_bridge