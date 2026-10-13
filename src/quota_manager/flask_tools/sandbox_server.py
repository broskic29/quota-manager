from flask import (
    Flask,
    render_template,
)

sandbox_app = Flask(__name__)

@sandbox_app.route("/")
def test():
    return render_template("sandbox.html")

if __name__ == "__main__":
    sandbox_app.run(debug=True)