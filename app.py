import zipfile
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from gtts import gTTS

app = Flask(__name__)
app.secret_key = "pdf-to-speech-secret-key"

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "outputs"

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

LANGUAGES = {
    "English (US)": "en",
    "French": "fr",
    "Spanish": "es",
    "German": "de",
    "Italian": "it",
}

VOICE_VARIANTS = {
    "Default": "com",
    "UK": "co.uk",
    "Australia": "com.au",
    "Canada": "ca",
    "India": "co.in",
}


def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    extracted_text = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            extracted_text.append(" ".join(text.split()))

    return "\n".join(extracted_text)


def chunk_text(text: str, max_chars: int = 4500) -> list[str]:
    if not text.strip():
        return []

    sentences = text.replace("!", ".").replace("?", ".").split(".")
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        candidate = f"{current_chunk}. {sentence}".strip(". ").strip()
        if len(candidate) <= max_chars:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk + ".")
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk + ".")

    return chunks


def generate_audio_files(chunks: list[str], output_subfolder: Path, lang: str, slow: bool, tld: str) -> list[str]:
    output_subfolder.mkdir(parents=True, exist_ok=True)
    generated_files = []

    for index, chunk in enumerate(chunks, start=1):
        filename = f"part_{index:03}.mp3"
        file_path = output_subfolder / filename
        tts = gTTS(text=chunk, lang=lang, slow=slow, tld=tld)
        tts.save(str(file_path))
        generated_files.append(filename)

    return generated_files


def zip_audio_folder(folder_path: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in folder_path.glob("*.mp3"):
            zipf.write(file, arcname=file.name)


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        file = request.files.get("pdf_file")
        if not file or file.filename == "":
            flash("Please choose a PDF file.")
            return redirect(url_for("home"))

        if not file.filename.lower().endswith(".pdf"):
            flash("Only PDF files are allowed.")
            return redirect(url_for("home"))

        language_name = request.form.get("language", "English (US)")
        speed_choice = request.form.get("speed", "normal")
        voice_variant_name = request.form.get("voice_variant", "Default")

        lang = LANGUAGES.get(language_name, "en")
        slow = speed_choice == "slow"
        tld = VOICE_VARIANTS.get(voice_variant_name, "com")

        safe_filename = secure_filename(file.filename)
        pdf_path = UPLOAD_FOLDER / safe_filename
        file.save(pdf_path)

        text = extract_text_from_pdf(pdf_path)
        if not text.strip():
            flash("No readable text found in the PDF.")
            return redirect(url_for("home"))

        chunks = chunk_text(text)
        if not chunks:
            flash("Could not split the PDF text into audio chunks.")
            return redirect(url_for("home"))

        folder_name = pdf_path.stem
        output_subfolder = OUTPUT_FOLDER / folder_name
        generated_files = generate_audio_files(chunks, output_subfolder, lang, slow, tld)

        zip_name = f"{folder_name}.zip"
        zip_file_path = OUTPUT_FOLDER / zip_name
        zip_audio_folder(output_subfolder, zip_file_path)

        return render_template(
            "result.html",
            files=generated_files,
            folder_name=folder_name,
            zip_name=zip_name,
            body_class="theme-light",
        )

    return render_template(
        "index.html",
        languages=LANGUAGES.keys(),
        voice_variants=VOICE_VARIANTS.keys(),
        body_class="theme-dark",
    )


@app.route("/download/<filename>")
def download_file(filename):
    file_path = OUTPUT_FOLDER / filename
    return send_file(file_path, as_attachment=True)


@app.route("/download-part/<folder>/<filename>")
def download_part(folder, filename):
    file_path = OUTPUT_FOLDER / folder / filename
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)