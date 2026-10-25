"""Quiz, Braille cards and Sign-language cards: separate sections that do not need the full lesson planner."""
import os


def run_special_output(intent, user_prompt, grade, subject, language, topic, cdc_context, sources,
                       material_text, num_questions, say, export_dir, file_tag) -> dict:
    os.makedirs(export_dir, exist_ok=True)
    stem = f"DraftBench_G{grade}_{subject.replace(' ', '_')}_{language.capitalize()}"
    result = {"intent": intent, "grade": grade, "subject": subject, "language": language,
              "sources": sources, "files": {}, "image_assets": []}

    if intent == "quiz":
        from agents.quiz_agent import build_quiz
        from utils.section_pdfs import generate_quiz_pdf
        quiz = build_quiz(user_prompt, grade, subject, language, cdc_context, material_text, topic, num_questions, say)
        if len(quiz["questions"]) < 3:
            return {**result, "error": "quiz_failed",
                    "message": "The AI couldn't write enough valid quiz questions. Try again, or choose fewer questions."}
        say("Building the quiz sheet...")
        path = os.path.join(export_dir, f"{stem}_Quiz{file_tag}.pdf")
        generate_quiz_pdf(quiz, path, grade, subject, language)
        result.update(files={"pdf": path}, response_text=f"Quiz with {len(quiz['questions'])} questions generated.")
        return result

    from agents.content_agent import build_key_content
    content = build_key_content(user_prompt, grade, subject, language, cdc_context, material_text, topic, say)

    if intent == "braille":
        from utils.section_pdfs import generate_braille_pdf
        if len(content["key_points"]) + len(content["key_terms"]) < 3:
            return {**result, "error": "content_failed",
                    "message": "The AI couldn't write enough content for the braille cards. Try again."}
        say("Converting to braille...")
        path = os.path.join(export_dir, f"{stem}_Braille{file_tag}.pdf")
        generate_braille_pdf(content, path, grade, subject, language)
        result.update(files={"pdf": path}, response_text="Braille cards generated.")
        return result

    if intent == "nsl":
        from agents.accessibility_tools import nsl_descriptions
        from utils.section_pdfs import generate_nsl_pdf
        if len(content["key_terms"]) < 2:
            return {**result, "error": "content_failed",
                    "message": "The AI couldn't find enough signable words for this topic. Try again."}
        items = nsl_descriptions(content["key_terms"], language, say)
        
        # --- USE THE SVG AGENT INSTEAD OF PIXART FOR INSTANT, CPU-FRIENDLY SIGN ICONS ---
        from agents.svg_agent import add_nsl_svg_illustrations
        items = add_nsl_svg_illustrations(items, topic if isinstance(topic, str) else "", say)
        
        say("Building the sign language cards...")
        path = os.path.join(export_dir, f"{stem}_NSL{file_tag}.pdf")
        generate_nsl_pdf(content, items, path, grade, subject, language)
        result.update(files={"pdf": path}, response_text="Sign language cards generated.")
        return result

    return {**result, "error": "unknown_intent", "message": f"Unknown output type: {intent}"}
