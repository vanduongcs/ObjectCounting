"""Pure UI state helpers for MainWindow button enable/disable rules."""


def compute_main_window_button_states(source_loaded, running, has_line, is_stream):
    return {
        "choose": not running,
        "camera": not running,
        "draw": source_loaded and not running,
        "rotate": source_loaded and not running,
        "timestamp": source_loaded and not running,
        "start": source_loaded and has_line and not running,
        "pause": running and not is_stream,
        "stop": running,
    }
