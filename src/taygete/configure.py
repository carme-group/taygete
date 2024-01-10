from __future__ import annotations

import io
import pathlib
import os
import subprocess
import sys
import textwrap
import tarfile
from typing import Callable

import httpx

from ncolony import ctllib


def homedir_jupyter(org_root: pathlib.Path) -> pathlib.Path:
    return org_root / "homedir"


def write_jupyter_config(org_root: pathlib.Path) -> None:
    etc_jupyter = org_root / "venv" / "jupyter" / "etc" / "jupyter"
    etc_jupyter.mkdir(exist_ok=True, parents=True)
    (etc_jupyter / "config.py").write_text(
        textwrap.dedent(
            f"""\
    c.NotebookApp.notebook_dir = '{os.fspath(homedir_jupyter(org_root) / "src")}'
    c.NotebookApp.allow_remote_access = True
    """
        )
    )


def land_starship(org_root: pathlib.Path, *, client: httpx.Client, run) -> None:
    base_url = "https://github.com/starship/starship/releases/latest/download/"
    proc = run(["uname", "-m"], check=True, capture_output=True, text=True)
    platform = proc.stdout.strip()
    fname = f"starship-{platform}-unknown-linux-musl.tar.gz"
    url = base_url + fname
    res = client.get(url)
    res.raise_for_status()
    content = res.content
    content_io = io.BytesIO(content)
    content_tar = tarfile.open(fileobj=content_io)
    [starship] = content_tar.getmembers()
    starship_contents = content_tar.extractfile(starship)
    starship_data = starship_contents.read()
    starship_loc = org_root / "venv" / "jupyter" / "bin" / "starship"
    starship_loc.parent.mkdir(exist_ok=True, parents=True)
    starship_loc.write_bytes(starship_data)
    starship_loc.chmod(0o755)


def basic_directories(org_root: pathlib.Path) -> None:
    hdj = homedir_jupyter(org_root)
    for subdir in ["venv", "src", ".ssh"]:
        (hdj / subdir).mkdir(parents=True, exist_ok=True)
    (hdj / ".ssh").chmod(0o700)


def ncolonize_jupyter(org_root: pathlib.Path):
    ncolony_root = org_root / "ncolony"
    subdirs = config, messages = [
        ncolony_root / part for part in ["config", "messages"]
    ]
    for a_subdir in subdirs:
        a_subdir.mkdir(parents=True, exist_ok=True)
    places = ctllib.Places(
        os.fspath(config),
        os.fspath(messages),
    )
    venv = org_root / "venv" / "jupyter"
    ctllib.add(
        places,
        "jupyter",
        os.fspath(venv / "bin" / "jupyter"),
        [
            "lab",
            "--config",
            os.fspath(venv / "etc" / "jupyter" / "config.py"),
            "--ip",
            "0.0.0.0",
        ],
        [f"HOME={os.fspath(homedir_jupyter(org_root))}", "SHELL=/bin/bash"],
        uid=1000,
    )


def configure_runtime(org_root, run=subprocess.run):
    with open("/etc/profile.d/add-venv.sh", "w") as fpout:
        fpout.write(f"PATH=$PATH:{os.fspath(org_root / 'venv' / 'jupyter' / '/bin')}")
    hdj, kernels = map(
        os.fspath,
        [
            homedir_jupyter(org_root),
            org_root / "venv" / "jupyter" / "share" / "jupyter" / "kernels",
        ],
    )
    run(["useradd", "developer", "--uid", "1000", "--home-dir", hdj], check=True)
    run(["chown", "-R", "developer", hdj, kernels], check=True)
    run(["apt-get", "update"], check=True)
    run(
        [
            "apt-get",
            "install",
            "-y",
            "texlive-latex-recommended",
            "texlive-latex-extra",
            "texlive-xetex",
            "poppler-utils",
            "nvi",
            "pandoc",
            "sudo",
        ]
    )


def configure_buildtime(
    org_root: pathlib.Path, *, client: httpx.Client, run: Callable
) -> None:
    write_jupyter_config(org_root)
    basic_directories(org_root)
    ncolonize_jupyter(org_root)
    land_starship(org_root, client=client, run=run)


def ncolony(org_root: pathlib.Path) -> None:
    python = os.fspath(org_root / "venv" / "jupyter" / "bin" / "python")
    ncolony_root = org_root / "ncolony"
    config, messages = map(
        os.fspath, [ncolony_root / part for part in ["config", "messages"]]
    )
    args = [
        python,
        "-m",
        "twisted",
        "ncolony",
        "--messages",
        messages,
        "--config",
        config,
    ]
    os.execv(args[0], args)


def main(argv=sys.argv, env=os.environ, run=subprocess.run):
    org_root = pathlib.Path(env["ORG_ROOT"])
    client = httpx.Client(verify=env.get("VERIFY_CA", True), follow_redirects=True)
    if argv[1] == "buildtime":
        configure_buildtime(org_root, client=client, run=run)
    elif argv[1] == "runtime":
        configure_runtime(org_root, run)
    elif argv[1] == "ncolony":
        ncolony(org_root)
    else:
        raise ValueError("unknown", argv[1])
