from __future__ import annotations

import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .config import get_settings


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailServiceError(RuntimeError):
    pass


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def _require_smtp_settings() -> None:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("SMTP_HOST", settings.smtp_host),
            ("SMTP_USERNAME", settings.smtp_username),
            ("SMTP_PASSWORD", settings.smtp_password),
            ("SMTP_FROM_EMAIL", settings.smtp_from_email),
        )
        if not value
    ]
    if missing:
        raise EmailServiceError(
            "Email delivery is not configured. Missing: " + ", ".join(missing)
        )


def _draw_wrapped_lines(pdf: canvas.Canvas, text: str, x: int, y: int, max_width: int) -> int:
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            y -= 14
            continue

        line = words[0]
        for word in words[1:]:
            candidate_line = f"{line} {word}"
            if pdf.stringWidth(candidate_line, "Helvetica", 10) <= max_width:
                line = candidate_line
                continue

            pdf.drawString(x, y, line)
            y -= 14
            line = word

        pdf.drawString(x, y, line)
        y -= 14

    return y


def _build_plain_text_raw_evaluation(project_handle: str, created_at: str) -> str:
    lines = [
        "ZynthClaw Public Goods Evaluation – Raw Data",
        "",
        f"Project: @{project_handle}",
        f"Generated: {created_at}",
        "",
        "Attached is a PDF containing the raw collated data used to build the impact evaluation:",
        "- Original X posts (tweets) pulled for the handle.",
        "- Filtered X replies collected for those posts.",
        "- Your detailed feedback from Telegram.",
        "- Optional GitHub developer-activity summary if a repo was provided.",
        "",
        "Open the PDF to review and re-interpret the signals in your own workflow.",
    ]
    return "\n".join(lines).strip()


def _build_html_raw_evaluation(project_handle: str, created_at: str) -> str:
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1f2937; line-height: 1.5;">
        <h2 style="margin-bottom: 8px;">ZynthClaw Public Goods Evaluation – Raw Data</h2>
        <p style="margin-top: 0;">Project: @{project_handle}</p>
        <p style="margin-top: 0;">Generated: {created_at}</p>
        <p>
          Attached is a PDF containing the raw collated data used to build the impact evaluation:
        </p>
        <ul>
          <li>Original X posts (tweets) pulled for the handle.</li>
          <li>Filtered X replies collected for those posts.</li>
          <li>Your detailed feedback from Telegram.</li>
          <li>Optional GitHub developer-activity summary if a repo was provided.</li>
        </ul>
        <p>
          Open the PDF to review and re-interpret the signals in your own workflow.
        </p>
      </body>
    </html>
    """


def _generate_raw_evaluation_pdf(evaluation: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    left = 50
    max_width = int(width - 100)
    y = int(height - 50)

    def ensure_space(min_y: int = 140) -> None:
        nonlocal y
        if y < min_y:
            pdf.showPage()
            y = int(height - 50)
            pdf.setFont("Helvetica", 10)

    def draw_block(title: str, text: str) -> None:
        nonlocal y
        ensure_space()

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(left, y, title)
        y -= 18
        pdf.setFont("Helvetica", 10)
        nonlocal_max = max_width
        y_local = _draw_wrapped_lines(pdf, text or "N/A", left, y, nonlocal_max)
        y = y_local - 12

    def draw_x_items(title: str, items: List[Dict[str, Any]]) -> None:
        nonlocal y
        ensure_space()
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(left, y, title)
        y -= 18
        pdf.setFont("Helvetica", 10)

        if not items:
            y = _draw_wrapped_lines(pdf, "N/A", left, y, max_width)
            y -= 12
            return

        for idx, item in enumerate(items, start=1):
            ensure_space()
            date = item.get("date") or ""
            likes = item.get("like_count", 0)
            retweets = item.get("retweet_count")
            replies = item.get("reply_count")
            header_parts = [f"{idx}. {date}".strip(), f"likes={likes}"]
            if retweets is not None:
                header_parts.append(f"retweets={retweets}")
            if replies is not None:
                header_parts.append(f"replies={replies}")
            header = " | ".join([p for p in header_parts if p])
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(left, y, header[:140])
            y -= 14

            pdf.setFont("Helvetica", 10)
            content = (item.get("content") or "").strip()
            y = _draw_wrapped_lines(pdf, content or "N/A", left, y, max_width)
            y -= 10

    def draw_x_threads(title: str, threads: List[Dict[str, Any]]) -> None:
        nonlocal y
        ensure_space()
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(left, y, title)
        y -= 18
        pdf.setFont("Helvetica", 10)

        if not threads:
            y = _draw_wrapped_lines(pdf, "N/A", left, y, max_width)
            y -= 12
            return

        for idx, th in enumerate(threads, start=1):
            ensure_space()
            post = th.get("post") or {}
            replies_local = th.get("replies") or []

            post_date = post.get("date") or ""
            post_likes = post.get("like_count", 0)
            post_author = post.get("author") or ""
            header = f"Post {idx} {('by @' + post_author) if post_author else ''} | {post_date} | likes={post_likes}"

            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(left, y, header[:140])
            y -= 14
            pdf.setFont("Helvetica", 10)

            post_text = (post.get("content") or "").strip()
            y = _draw_wrapped_lines(pdf, post_text or "N/A", left, y, max_width)
            y -= 8

            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(left, y, f"Replies (filtered): {len(replies_local)}")
            y -= 14
            pdf.setFont("Helvetica", 10)

            if not replies_local:
                y = _draw_wrapped_lines(pdf, "No replies captured (or they were filtered).", left, y, max_width)
                y -= 10
                continue

            for ridx, r in enumerate(replies_local, start=1):
                ensure_space()
                author = r.get("author") or ""
                prefix = f"- @{author}: " if author else "- "
                text = (r.get("content") or "").strip()
                y = _draw_wrapped_lines(pdf, (prefix + text)[:1200] or "- N/A", left, y, max_width)
                y -= 6

            y -= 8

    pdf.setTitle("ZynthClaw Public Goods Evaluation – Raw Data")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(left, y, "ZynthClaw Public Goods Evaluation – Raw Data")
    y -= 24

    pdf.setFont("Helvetica", 10)
    header = (
        f"Project: @{evaluation.get('x_handle', 'unknown')}  |  "
        f"Generated: {evaluation.get('created_at', '')}"
    )
    pdf.drawString(left, y, header)
    y -= 24

    draw_block("Community sentiment summary", evaluation.get("community_sentiment_summary", ""))
    draw_block("User feedback (Telegram)", evaluation.get("user_feedback", ""))
    draw_block("Optional additional info (user-provided)", evaluation.get("optional_user_info", ""))

    # Raw X data: prefer threads (post -> replies) for manual review.
    threads = evaluation.get("x_threads") or []
    if threads:
        draw_x_threads(f"X posts and replies (threads) (posts: {len(threads)})", threads)
    else:
        tweets = evaluation.get("x_raw_tweets") or []
        replies = evaluation.get("x_raw_replies") or []
        draw_x_items(f"X raw tweets (count: {len(tweets)})", tweets)
        draw_x_items(f"X raw replies (filtered) (count: {len(replies)})", replies)

    if evaluation.get("github_repo_url"):
        gh_text = (
            f"Repository: {evaluation.get('github_repo_url')}\n\n"
            f"{evaluation.get('github_summary', '')}"
        )
        draw_block("GitHub developer activity", gh_text)

    draw_block(
        "Impact classification and mechanism design",
        (
            f"Impact classification: {evaluation.get('impact_classification', 'N/A')}\n\n"
            f"{evaluation.get('mechanism_design_recommendation', '')}"
        ),
    )

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def send_raw_evaluation_email(recipient_email: str, evaluation: Dict[str, Any]) -> None:
    recipient_email = recipient_email.strip()
    if not is_valid_email(recipient_email):
        raise EmailServiceError("Please provide a valid email address.")

    _require_smtp_settings()

    handle = evaluation.get("x_handle", "unknown")
    created_at = evaluation.get("created_at", datetime.now(timezone.utc).isoformat())

    settings = get_settings()
    message = EmailMessage()
    message["Subject"] = "ZynthClaw Public Goods Evaluation – Raw Data"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient_email

    plain_text = _build_plain_text_raw_evaluation(handle, created_at)
    html = _build_html_raw_evaluation(handle, created_at)
    message.set_content(plain_text)
    message.add_alternative(html, subtype="html")
    message.add_attachment(
        _generate_raw_evaluation_pdf(evaluation),
        maintype="application",
        subtype="pdf",
        filename="zynthclaw_public_goods_raw_evaluation.pdf",
    )

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

