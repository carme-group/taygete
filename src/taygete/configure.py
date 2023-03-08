import pathlib
import os
import subprocess
import sys

from ncolony  import ctllib

def homedir_jupyter(org_root: pathlib.Path) -> pathlib.Path:
    return org_root / "homedir"


def write_jupyter_config(org_root: pathlib.Path) -> None:
    etc_jupyter = org_root / "venv" / "jupyter" / "etc" / "jupyter"
    etc_jupyter.mkdir(exist_ok=True, parent=True)
    (etc_jupyter / "config.py").write_text(textwrap.dedent(f"""\
    c.NotebookApp.notebook_dir = '{os.fspath(homedir_jupyter(org_root) / "src")}'
    c.NotebookApp.allow_remote_access = True
    """))


def basic_directories(org_root: pathlib.Path) -> None:
    hdj = homedir_jupyter(org)
    for subdir in ["venv", "src", ".ssh"]:
        (hdj / subdir).mkdir(parent=True, exist_ok=True)
    (hdj / ".ssh").chmod(0o700)

def ncolonize_jupyter(org_root: pathlib.Path):
    ncolony_root = pathlib.Path(org_dir) / "ncolony"
    places = ctllib.Places(
        os.fspath(ncolony_root / "config"),
        os.fspath(ncolony_root / "messages"),
    )
    venv = pathlib.Path(org_dir) / "venv" / "jupyter"
    ctllib.add(places, "jupyter", os.fspath(venv / "bin" / "jupyter"),
               ["lab", "--config", os.fspath(venv / "etc"/ "jupyter" / "config.py"),
                "--ip", "0.0.0.0"], dict(HOME=os.fspath(homedir_jupyter(org_dir)), SHELL="/bin/bash"),
                uid=1000)

def configure_runtime(org_root, run=subprocess.run):
    with open("/etc/bash.bashrc", "a+") as fpout:
        fpout.write(f"PATH=$PATH:{os.fspath(org_root / 'venv' / 'jupyter' / '/bin')}")
    hdj, kernels = map(os.fspath, [homedir_jupyter(org_root), org_root / "venv" / "jupyter" / "share" / "jupyter" / "kernels"])
    run(["useradd", "--uid", "1000", "--homedir", hdj], check=True)
    run(["chown", "-R", "developer", hdj, kernels], check=True)
    run(["apt-get", "update"], check=True)
    run(["apt-get", "install", "texlive-latex-recommended", "texlive-latex-extra", "texlive-xetex", "poppler-utils", "nvi", "pandoc"])


def configure_buildtime(org_root: pathlib.Path) -> None:
    write_jupyter_config(org_root)
    basic_directories(org_root)
    ncolonize_jupyter(org_root)

    
def main(argv=sys.argv, env=os.environ, run=subprocess.run):
    org_root = pathlib.Path(env["ORG_ROOT"])
    if argv[1] == "buildtime":
        configure_buildtime(org_root)
    elif argv[2] == "runtime":
        configure_runtime(org_root, run)
    else:
        raise ValueError("unknown", argv[1])
