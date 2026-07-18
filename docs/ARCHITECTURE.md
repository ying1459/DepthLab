# Architecture

Depth Lab is intentionally local-first and split into three layers:

1. `app/static/` provides the HTML, CSS, and JavaScript interface.
2. `app/main.py` runs a FastAPI service bound to `127.0.0.1`, owns job state, and serves previews/results.
3. `app/worker.py` starts model inference in a spawned child process. The parent process remains responsive and can terminate a cancelled job without waiting for CPU inference to yield.

`app/depth_engine.py` handles frame sampling, Depth Anything V2 inference, temporal normalization, colorization, and FFmpeg finalization. Windows builds are hosted by pywebview and bundle the Small checkpoint for offline use.

The application accepts a source video, writes job files under the user's local application-data directory, and exposes them only through the loopback service. No cloud API is used by the packaged application.
