# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Default HTML pages for AsgiServer.

Contains HTML templates for default server pages when no content is configured.
"""

DEFAULT_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>genro-asgi</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e4e4e4;
        }
        .container { text-align: center; padding: 40px; }
        h1 { font-size: 3rem; font-weight: 300; margin-bottom: 20px; color: #fff; }
        h1 span { color: #0ea5e9; }
        .status { font-size: 1.2rem; color: #22c55e; margin-bottom: 30px; }
        .message { font-size: 1rem; color: #94a3b8; max-width: 400px; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="container">
        <h1>genro<span>-asgi</span></h1>
        <p class="status">Server is running</p>
        <p class="message">
            No content has been configured yet.
            Mount your applications or add routes to get started.
        </p>
    </div>
</body>
</html>"""
