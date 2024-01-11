from __future__ import annotations

import io
import pathlib
import os
import shutil
import subprocess
import sys
import textwrap
import tarfile
from typing import Callable, Sequence, Mapping

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


def configure_helm_build(
    org_root: pathlib.Path, *, client: httpx.Client, run: Callable
) -> None:
    raw_key = client.get("https://baltocdn.com/helm/signing.asc")
    raw_key.raise_for_status()
    content = raw_key.content
    res = run(
        ["gpg", "--dearmor"], input=content, capture_output=True, check=True, text=False
    )
    helm_dir = homedir_jupyter(org_root) / "helm"
    helm_dir.mkdir(parents=True, exist_ok=True)
    keyring = helm_dir / "helm.gpg"
    keyring.write_bytes(res.stdout)
    res = run(
        ["dpkg", "--print-architecture"], capture_output=True, check=True, text=True
    )
    architecture = res.stdout.strip()
    deb_line = (
        f"deb [arch={architecture} signed-by={os.fspath(keyring)}]"
        " https://baltocdn.com/helm/stable/debian/ all main"
    )
    deb_file = helm_dir / "helm-stable-debian.list"
    deb_file.write_text(deb_line)


def land_starship(
    org_root: pathlib.Path, *, client: httpx.Client, run: Callable
) -> None:
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
    if starship_contents is None:
        raise ValueError(url, "did not have a starship binary in it")
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


def ncolonize_jupyter(org_root: pathlib.Path) -> None:
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


def configure_runtime(org_root, run: Callable = subprocess.run) -> None:
    with open("/etc/profile.d/taygete.sh", "w") as fpout:
        print(
            f"export PATH={os.fspath(org_root / 'venv' / 'jupyter' / 'bin')}:$PATH",
            file=fpout,
        )
        print("export WORKON_HOME=~/venv", file=fpout)
        print("cd ~", file=fpout)
    pathlib.Path("/etc/sudoers.d").mkdir(exist_ok=True)
    with open("/etc/sudoers.d/developer", "w") as fpout:
        print("developer            ALL = (ALL) NOPASSWD: ALL", file=fpout)
    run(["apt-get", "update"], check=True)
    run(["apt-get", "install", "--yes", "apt-transport-https"], check=True)
    helm_dir = homedir_jupyter(org_root) / "helm"
    orig_file = helm_dir / "helm-stable-debian.list"
    run(["cat", os.fspath(orig_file)])
    shutil.copy(orig_file, "/etc/apt/sources.list.d/")
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
            "docker.io",
            "kubernetes-client",
            "helm",
        ],
        check=True,
    )


def configure_buildtime(
    org_root: pathlib.Path, *, client: httpx.Client, run: Callable
) -> None:
    write_jupyter_config(org_root)
    basic_directories(org_root)
    ncolonize_jupyter(org_root)
    configure_helm_build(org_root, client=client, run=run)
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


def main(
    argv: Sequence[str] = sys.argv,
    env: Mapping[str, str] = os.environ,
    run: Callable = subprocess.run,
) -> None:
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
