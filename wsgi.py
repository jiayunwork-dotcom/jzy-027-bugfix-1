"""单容器对外服务入口：gunicorn/wsgi 或 flask run 均可，默认可直接
`python wsgi.py` 起服务。容器里用 Flask 内建线程化服务器即可。
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
