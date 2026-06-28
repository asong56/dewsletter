from pathlib import Path
import zipfile

DB = Path("current.db")
PROXY = Path("proxy.txt")
OUT = Path("output.zip")


def main():
    with zipfile.ZipFile(OUT, "w") as z:

        if DB.exists():
            z.write(DB, "current.db")

        if PROXY.exists():
            z.write(PROXY, "proxy.txt")


if __name__ == "__main__":
    main()
