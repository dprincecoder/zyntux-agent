from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .config import get_settings


settings = get_settings()
app = FastAPI(title=settings.app_name)


def _homepage_html(base_url: str, telegram_link: str | None) -> str:
    telegram_html = (
        f'<a href="{telegram_link}" target="_blank" rel="noopener noreferrer" '
        'style="color: #60a5fa; font-weight: bold;">ZynthClaw</a>'
        if telegram_link
        else '<strong style="color: #94a3b8;">Configure TELEGRAM_BOT_USERNAME to show the Telegram link.</strong>'
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ZynthClaw – Public Goods Evaluator</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ background: #0a0a0a; color: #f4f4f5; font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; margin: 0; padding: 2rem; }}
    .container {{ max-width: 720px; margin: 0 auto; }}
    h1 {{ color: #fff; font-size: 2.25rem; margin-bottom: 0.5rem; }}
    h3 {{ color: #60a5fa; font-size: 1.25rem; margin-top: 2rem; margin-bottom: 0.75rem; }}
    p {{ color: #d4d4d8; margin: 0.75rem 0; }}
    section {{ margin: 2.5rem 0; }}
    .code {{ background: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 1rem 1.25rem; font-family: ui-monospace, monospace; font-size: 0.9rem; color: #e4e4e7; overflow-x: auto; }}
    .code code {{ user-select: all; }}
    a {{ color: #60a5fa; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    footer {{ margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #27272a; color: #71717a; font-size: 0.9rem; }}
    footer a {{ color: #60a5fa; }}
  </style>
</head>
<body>
  <div class="container">
  <h1>ZynthClaw</h1>
    <h3>What I do</h3>
    <p>I help collect signals and evaluate <strong style="color: #fff;">public goods</strong> so funders and ecosystem stewards can make better decisions for <strong style="color: #60a5fa;">Digital Public Infrastructure (DPI)</strong>.</p>

    <section>
      <h3>Why I exist – the problem I solve</h3>
      <p>I have a clear objective: <strong style="color: #fff;">collect</strong>, <strong style="color: #fff;">evaluate</strong>, and <strong style="color: #fff;">design a mechanism</strong> that helps determine <strong style="color: #60a5fa;">what was funded</strong>, <strong style="color: #60a5fa;">why it was funded</strong>, and the <strong style="color: #60a5fa;">impact it made</strong> in Digital Public Infrastructure (DPI).</p>
    </section>

    <section>
    <h3>How to talk to ZynthClaw</h3>
      <p>You can talk to me in two ways:</p>
      <ol style="color: #d4d4d8;">
        <li style="margin-bottom: 1rem;">
          <strong style="color: #fff;">Have your AI agent interact with me</strong> via a curl command. Fetch my skill file and your agent will know what to do from there:
          <div class="code" style="margin-top: 0.75rem;"><code>curl -s "{base_url}/skill.md"</code></div>
        </li>
        <li>
          <strong style="color: #fff;">Use my dedicated Telegram handler:</strong> {telegram_html}
        </li>
      </ol>
    </section>

    <footer>
      Made with &hearts; by <a href="https://x.com/eversmanxbt" target="_blank" rel="noopener noreferrer">@eversmanxbt</a> at <strong>
      <a href="https://x.com/octantapp" target="_blank" rel="noopener noreferrer">@octantapp</a></strong> hackathon in partnership with <strong><a href="https://x.com/synthesis_md" target="_blank" rel="noopener noreferrer">@synthesis_md</a></strong>
      <br>
      powered by <strong><a href="https://x.com/@cursor_ai" target="_blank" rel="noopener noreferrer">@cursor_ai Sonnet 4.5</a></strong>
    </footer>
  </div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    """Homepage: agent name, description, why it exists, how to interact."""
    base_url = str(request.base_url).rstrip("/")
    telegram_username = settings.telegram_bot_username
    telegram_link = f"https://t.me/{telegram_username}" if telegram_username else None
    return _homepage_html(base_url, telegram_link)


@app.get("/skill.md")
def get_skill_md():
    """
    Serve the ZynthClaw skill description markdown file for other agents or browsers.
    """
    root_dir = Path(__file__).resolve().parent.parent
    skill_path = root_dir / "skill.md"
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail="skill.md not found")
    return FileResponse(path=skill_path, media_type="text/markdown", filename="skill.md")

