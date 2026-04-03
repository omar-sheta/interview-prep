"""REST endpoint registration for the interview server."""

from types import SimpleNamespace

from fastapi import Depends, HTTPException
from fastapi.responses import Response


def register_rest_routes(fast_app, deps):
    """Register REST endpoints and return the bound handler functions."""

    async def health_check():
        """Health check endpoint with LangGraph sanity verification."""
        try:
            graph = deps.build_sanity_check_graph()
            result = graph.invoke({"value": "health_check"})
            langgraph_ok = "processed by Node A" in result["value"]
        except Exception:
            langgraph_ok = False

        return {
            "status": "ready" if langgraph_ok else "degraded",
            "agent_engine": "langgraph",
            "mlx_gpu": deps.mx.metal.is_available() if deps.mx else False,
            "qdrant_status": deps.check_qdrant_status(),
        }

    async def root():
        """Root endpoint with basic API info."""
        return {
            "name": "BeePrepared API",
            "version": "0.2.0",
            "engine": "LangGraph",
            "features": ["STT", "TTS", "LLM Streaming"],
            "docs": "/docs",
        }

    async def get_user_progress_api(
        user_id: str,
        auth_user_id: str = Depends(deps.get_authenticated_rest_user_id),
    ):
        """Get user's overall progress and statistics."""
        if user_id != auth_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        user_db = deps.get_user_db()
        progress = user_db.get_user_progress(user_id)
        user = user_db.get_user(user_id)

        return {
            "user": deps.safe_user_payload(user),
            "progress": progress,
        }

    async def get_user_sessions_api(
        user_id: str,
        limit: int = 10,
        auth_user_id: str = Depends(deps.get_authenticated_rest_user_id),
    ):
        """Get user's interview session history."""
        if user_id != auth_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        user_db = deps.get_user_db()
        sessions_list = user_db.get_session_history(user_id, limit)
        return {"sessions": sessions_list}

    async def get_session_details_api(
        session_id: str,
        auth_user_id: str = Depends(deps.get_authenticated_rest_user_id),
    ):
        """Get full details of a specific interview session."""
        user_db = deps.get_user_db()
        session_details = user_db.get_session_details(session_id)

        if not session_details:
            raise HTTPException(status_code=404, detail="Session not found")

        if session_details.get("user_id") != auth_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        return session_details

    async def export_session_pdf(
        session_id: str,
        auth_user_id: str = Depends(deps.get_authenticated_rest_user_id),
    ):
        """Export interview session as a downloadable PDF report using ReportLab."""
        import io

        try:
            from reportlab.lib import colors
            from reportlab.lib.colors import HexColor
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                HRFlowable,
                KeepTogether,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as import_err:
            raise HTTPException(
                status_code=503,
                detail=(
                    "PDF export is unavailable because the active Python environment is missing "
                    "the 'reportlab' package."
                ),
            ) from import_err

        user_db = deps.get_user_db()
        details = user_db.get_session_details(session_id)
        if not details:
            raise HTTPException(status_code=404, detail="Session not found")
        if details.get("user_id") != auth_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        summary = details.get("summary") or {}
        answers = details.get("answers") or []
        job_title = details.get("job_title") or "Interview"
        avg_score = details.get("average_score") or summary.get("average_score", 0)
        started = (details.get("started_at") or "")[:19]
        total_q = details.get("total_questions")
        if total_q is None:
            total_q = len(answers)
        answered_q = details.get("answered_questions")
        if answered_q is None:
            answered_q = len(answers)

        dim_labels = {
            "relevance": "Relevance",
            "depth": "Depth",
            "structure": "Structure",
            "specificity": "Specificity",
            "communication": "Communication",
            "clarity": "Clarity",
            "accuracy": "Accuracy",
            "completeness": "Completeness",
        }

        BRAND = HexColor("#6366F1")
        DARK = HexColor("#1E293B")
        MUTED = HexColor("#64748B")
        SUCCESS = HexColor("#22C55E")
        WARN = HexColor("#EAB308")
        DANGER = HexColor("#EF4444")
        BORDER = HexColor("#E2E8F0")
        LIGHT = HexColor("#F8FAFC")

        def _score_color(score):
            try:
                value = float(score)
            except (TypeError, ValueError):
                return MUTED
            if value >= 7:
                return SUCCESS
            if value >= 5:
                return WARN
            return DANGER

        def _esc(text):
            if not text:
                return ""
            return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                "Title2",
                parent=styles["Title"],
                fontSize=20,
                textColor=DARK,
                spaceAfter=4,
                leading=24,
            )
        )
        styles.add(
            ParagraphStyle(
                "Subtitle",
                parent=styles["Normal"],
                fontSize=12,
                textColor=BRAND,
                spaceAfter=12,
            )
        )
        styles.add(
            ParagraphStyle(
                "SectionHead",
                parent=styles["Heading2"],
                fontSize=13,
                textColor=DARK,
                spaceBefore=14,
                spaceAfter=6,
                borderWidth=0,
            )
        )
        styles.add(
            ParagraphStyle(
                "SubHead",
                parent=styles["Heading3"],
                fontSize=10,
                textColor=DARK,
                spaceBefore=8,
                spaceAfter=4,
            )
        )
        styles.add(
            ParagraphStyle(
                "Body",
                parent=styles["Normal"],
                fontSize=9,
                textColor=DARK,
                leading=13,
                spaceAfter=4,
            )
        )
        styles.add(
            ParagraphStyle(
                "BodyItalic",
                parent=styles["Body"],
                fontName="Helvetica-Oblique",
            )
        )
        styles.add(
            ParagraphStyle(
                "Meta",
                parent=styles["Normal"],
                fontSize=9,
                textColor=MUTED,
                leading=12,
            )
        )
        bullet_style = styles["Bullet"]
        bullet_style.parent = styles["Body"]
        bullet_style.leftIndent = 14
        bullet_style.bulletIndent = 4
        bullet_style.spaceBefore = 1
        bullet_style.spaceAfter = 1
        styles.add(
            ParagraphStyle(
                "Footer",
                parent=styles["Normal"],
                fontSize=8,
                textColor=MUTED,
                alignment=TA_CENTER,
                spaceBefore=20,
            )
        )
        styles.add(
            ParagraphStyle(
                "QHeader",
                parent=styles["Normal"],
                fontSize=10,
                fontName="Helvetica-Bold",
                textColor=DARK,
                leading=13,
            )
        )
        styles.add(
            ParagraphStyle(
                "SmallMuted",
                parent=styles["Normal"],
                fontSize=8,
                textColor=MUTED,
                leading=11,
            )
        )

        story = []
        story.append(Paragraph("Interview Report", styles["Title2"]))
        story.append(Paragraph(_esc(job_title), styles["Subtitle"]))

        meta_lines = [
            f"<b>Date:</b> {_esc(started or 'N/A')}",
            f"<b>Questions:</b> {answered_q}/{total_q} answered",
            f"<b>Average Score:</b> {avg_score}/10",
        ]
        story.append(Paragraph("<br/>".join(meta_lines), styles["Meta"]))
        story.append(Spacer(1, 8))

        breakdown = summary.get("overall_breakdown") or summary.get("score_breakdown") or {}
        if breakdown:
            story.append(Paragraph("Dimension Scores", styles["SectionHead"]))
            story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=6))

            table_data = [["Dimension", "Score"]]
            row_colors = []
            for dim, value in breakdown.items():
                table_data.append([dim_labels.get(dim, dim.title()), f"{value}/10"])
                row_colors.append(_score_color(value))

            table = Table(table_data, colWidths=[140, 60])
            style_cmds = [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, colors.white]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
            for index, color in enumerate(row_colors):
                style_cmds.append(("TEXTCOLOR", (1, index + 1), (1, index + 1), color))
                style_cmds.append(("FONTNAME", (1, index + 1), (1, index + 1), "Helvetica-Bold"))
            table.setStyle(TableStyle(style_cmds))
            story.append(table)
            story.append(Spacer(1, 8))

        telemetry = summary.get("telemetry") or {}
        if telemetry:
            story.append(Paragraph("Speech Analytics", styles["SectionHead"]))
            story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=6))
            speech_lines = [
                f"<b>Filler Words:</b> {telemetry.get('fillerWords', 0)}  ({telemetry.get('fillersPerMinute', 0)}/min)",
                f"<b>Hedge Words:</b> {telemetry.get('hedge_words', 0)}",
                f"<b>Confidence:</b> {_esc(str(telemetry.get('confidence', 'N/A')))}",
            ]
            star = telemetry.get("star_analysis") or {}
            if star:
                components = ["Situation", "Task", "Action", "Result"]
                detected = [component for component in components if star.get(component.lower())]
                speech_lines.append(
                    f"<b>STAR Framework:</b> {star.get('score', 0)}/4"
                    f" ({', '.join(detected) if detected else 'None detected'})"
                )
            story.append(Paragraph("<br/>".join(speech_lines), styles["Meta"]))
            story.append(Spacer(1, 8))

        overall_feedback = summary.get("overall_feedback")
        top_strengths = summary.get("top_strengths") or []
        improvements = summary.get("areas_to_improve") or []
        actions = summary.get("action_items") or []
        communication = summary.get("communication_feedback")

        if overall_feedback or top_strengths or improvements:
            story.append(Paragraph("Overall Feedback", styles["SectionHead"]))
            story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=6))
            if overall_feedback:
                story.append(Paragraph(_esc(overall_feedback), styles["Body"]))
            if top_strengths:
                story.append(Paragraph("Strengths", styles["SubHead"]))
                for strength in top_strengths:
                    story.append(Paragraph(_esc(strength), styles["Bullet"], bulletText="\u2022"))
            if improvements:
                story.append(Paragraph("Areas to Improve", styles["SubHead"]))
                for area in improvements:
                    story.append(Paragraph(_esc(area), styles["Bullet"], bulletText="\u2022"))
            if actions:
                story.append(Paragraph("Action Items", styles["SubHead"]))
                for action in actions:
                    story.append(Paragraph(_esc(action), styles["Bullet"], bulletText="\u2022"))
            if communication:
                story.append(Paragraph("Communication Feedback", styles["SubHead"]))
                story.append(Paragraph(_esc(communication), styles["Body"]))
            story.append(Spacer(1, 6))

        if answers:
            story.append(Paragraph("Per-Question Breakdown", styles["SectionHead"]))
            story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=8))

            for answer in answers:
                q_num = answer.get("question_number", "?")
                q_text = answer.get("question_text", "Question")
                evaluation = answer.get("evaluation") or {}
                score = evaluation.get("score", 0)
                skipped = answer.get("skipped", False)
                score_color = _score_color(score)

                q_elements = []
                skip_tag = " <i>(Skipped)</i>" if skipped else ""
                score_html = f'<font color="{score_color.hexval()}">{score}/10</font>'
                q_elements.append(
                    Paragraph(
                        f"Q{q_num}: {_esc(q_text)}  —  {score_html}{skip_tag}",
                        styles["QHeader"],
                    )
                )

                category = answer.get("category", "General")
                score_breakdown = evaluation.get("score_breakdown") or {}
                meta_parts = [f"Category: {_esc(category)}"]
                if score_breakdown:
                    dims_str = " | ".join(
                        f"{dim_labels.get(dim, dim.title())}: {value}"
                        for dim, value in score_breakdown.items()
                    )
                    meta_parts.append(dims_str)
                q_elements.append(Paragraph(" &nbsp;&nbsp; ".join(meta_parts), styles["SmallMuted"]))
                q_elements.append(Spacer(1, 4))

                user_answer = answer.get("user_answer") or ""
                if user_answer and user_answer != "(Skipped)":
                    snippet = user_answer[:600] + ("..." if len(user_answer) > 600 else "")
                    q_elements.append(Paragraph("Your Answer", styles["SubHead"]))
                    q_elements.append(Paragraph(f"<i>{_esc(snippet)}</i>", styles["Body"]))

                reasoning = evaluation.get("evaluation_reasoning") or evaluation.get("feedback") or ""
                if reasoning:
                    q_elements.append(Paragraph("Assessment", styles["SubHead"]))
                    q_elements.append(Paragraph(_esc(reasoning), styles["Body"]))

                strengths = evaluation.get("strengths") or []
                gaps = (
                    evaluation.get("gaps")
                    or evaluation.get("rubric_misses")
                    or evaluation.get("missing_concepts")
                    or []
                )
                if strengths:
                    q_elements.append(
                        Paragraph(
                            f'<font color="{SUCCESS.hexval()}"><b>Strengths:</b> {_esc(", ".join(strengths[:4]))}</font>',
                            styles["Body"],
                        )
                    )
                if gaps:
                    q_elements.append(
                        Paragraph(
                            f'<font color="{DANGER.hexval()}"><b>Gaps:</b> {_esc(", ".join(gaps[:4]))}</font>',
                            styles["Body"],
                        )
                    )

                tip = evaluation.get("coaching_tip")
                if tip:
                    q_elements.append(
                        Paragraph(
                            f'<font color="{BRAND.hexval()}"><b>Tip:</b></font> {_esc(tip)}',
                            styles["Body"],
                        )
                    )

                model_answer = evaluation.get("model_answer") or evaluation.get("optimized_answer") or ""
                if model_answer:
                    q_elements.append(Paragraph("Model Answer", styles["SubHead"]))
                    q_elements.append(
                        Paragraph(
                            _esc(model_answer[:800] + ("..." if len(model_answer) > 800 else "")),
                            styles["BodyItalic"],
                        )
                    )

                q_elements.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=BORDER,
                        spaceBefore=6,
                        spaceAfter=8,
                    )
                )
                story.append(KeepTogether(q_elements))

        story.append(Paragraph("Generated by BeePrepared", styles["Footer"]))

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=f"Interview Report - {job_title}",
            author="BeePrepared",
        )
        doc.build(story)
        pdf_bytes = buf.getvalue()

        safe_title = "".join(c for c in job_title if c.isalnum() or c in " -_")[:40].strip() or "interview"
        filename = f"BeePrepared_{safe_title}_{started[:10]}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def get_career_analyses_api(
        user_id: str,
        limit: int = 5,
        auth_user_id: str = Depends(deps.get_authenticated_rest_user_id),
    ):
        """Get user's career analysis history."""
        if user_id != auth_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        user_db = deps.get_user_db()
        analyses = user_db.get_career_analyses(user_id, limit)
        return {"analyses": analyses}

    fast_app.add_api_route("/health", health_check, methods=["GET"])
    fast_app.add_api_route("/", root, methods=["GET"])
    fast_app.add_api_route("/api/user/{user_id}/progress", get_user_progress_api, methods=["GET"])
    fast_app.add_api_route("/api/user/{user_id}/sessions", get_user_sessions_api, methods=["GET"])
    fast_app.add_api_route("/api/session/{session_id}", get_session_details_api, methods=["GET"])
    fast_app.add_api_route("/api/session/{session_id}/export", export_session_pdf, methods=["GET"])
    fast_app.add_api_route("/api/user/{user_id}/career_analyses", get_career_analyses_api, methods=["GET"])

    return SimpleNamespace(
        health_check=health_check,
        root=root,
        get_user_progress_api=get_user_progress_api,
        get_user_sessions_api=get_user_sessions_api,
        get_session_details_api=get_session_details_api,
        export_session_pdf=export_session_pdf,
        get_career_analyses_api=get_career_analyses_api,
    )
