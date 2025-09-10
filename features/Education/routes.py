from flask import Blueprint, render_template

bp = Blueprint(
    "education",
    __name__,
    url_prefix="/education",
    template_folder="templates",
)

@bp.get("/video-tutorials")
def show_video_tutorials():
    # Renders the same page you already have, just relocated under this feature.
    return render_template("video-tutorials.html")
