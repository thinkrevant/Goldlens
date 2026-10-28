"""Run the GoldLens website:  python -m goldlens.web  [--port 8000] [--host 127.0.0.1]"""
import argparse

import uvicorn


def main():
    ap = argparse.ArgumentParser(description="GoldLens website")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run("goldlens.web.server:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
